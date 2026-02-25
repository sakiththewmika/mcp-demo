import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

def clean_schema(schema):
    """Remove additionalProperties from schema as Gemini doesn't support it"""
    if isinstance(schema, dict):
        cleaned = {k: v for k, v in schema.items() if k != "additionalProperties"}
        for key, value in cleaned.items():
            if isinstance(value, dict):
                cleaned[key] = clean_schema(value)
            elif isinstance(value, list):
                cleaned[key] = [clean_schema(item) if isinstance(item, dict) else item for item in value]
        return cleaned
    return schema

async def main():
    # 1. Configuration for the MCP Server
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"] # Ensure this filename matches your server script
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 2. Get tools from MCP server and convert them for Gemini
            mcp_tools = await session.list_tools()
            gemini_tools = [
                types.Tool(
                    function_declarations=[
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": clean_schema(tool.inputSchema),
                        } for tool in mcp_tools.tools
                    ]
                )
            ]

            # 3. Setup Gemini Client
            client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
            model_id = "gemini-2.5-flash-lite" 

            user_query = "What is the status of vehicle 102?"
            
            # 4. First request to Gemini with the tool definitions
            response = client.models.generate_content(
                model=model_id,
                contents=user_query,
                config=types.GenerateContentConfig(tools=gemini_tools)
            )

            # 5. Handle the tool call loop (Gemini tells us what to call)
            # This logic checks if Gemini wants to call a function
            if response.candidates[0].content.parts[0].function_call:
                fc = response.candidates[0].content.parts[0].function_call
                print(f"--- Gemini requested tool: {fc.name} with args {fc.args} ---")
                
                # Execute the tool on the MCP Server
                result = await session.call_tool(fc.name, fc.args)
                
                # Send the result back to Gemini for the final answer
                final_response = client.models.generate_content(
                    model=model_id,
                    contents=[
                        types.Content(role="user", parts=[types.Part.from_text(text=user_query)]),
                        response.candidates[0].content, # Original model response
                        types.Content(role="tool", parts=[
                            types.Part.from_function_response(
                                name=fc.name,
                                response={"result": result.content[0].text}
                            )
                        ])
                    ],
                    config=types.GenerateContentConfig(tools=gemini_tools)
                )
                try:
                    answer = final_response.text if final_response.text else "No text response"
                except:
                    if final_response.candidates and final_response.candidates[0].content.parts:
                        part = final_response.candidates[0].content.parts[0]
                        answer = part.text if hasattr(part, 'text') else str(part)
                    else:
                        answer = "No response generated"
                print(f"\nFinal AI Answer: {answer}")
            else:
                print(f"AI Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(main())