import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp import ClientSession
from mcp.client.sse import sse_client

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
    server_url = "http://localhost:8000/sse"

    async with sse_client(server_url) as (read, write):
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
            model_id = "gemini-2.5-flash" 

            # determine user query: prefer command-line args, otherwise prompt
            import sys
            if len(sys.argv) > 1:
                user_query = " ".join(sys.argv[1:])
            else:
                user_query = input("Enter your query: ")
            
            # 4. First request to Gemini with the tool definitions
            print("Available tools from MCP server:")
            for t in mcp_tools.tools:
                print(f" - {t.name}: {t.description} (inputSchema={t.inputSchema})")

            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=user_query,
                    config=types.GenerateContentConfig(tools=gemini_tools)
                )
            except Exception as e:
                print(f"API call failed: {e}")
                return

            # 5. Handle the tool call loop (Gemini tells us what to call). We'll
            # keep sending back tool results until the model returns a plain text
            # answer.
            conversation_contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_query)])]
            conversation_contents.append(response.candidates[0].content)

            final_answer = None
            while True:
                parts = response.candidates[0].content.parts
                if parts and parts[0].function_call:
                    fc = parts[0].function_call
                    print(f"--- Gemini requested tool: {fc.name} with args {fc.args} ---")
                    result = await session.call_tool(fc.name, fc.args)
                    # debug: show raw result object
                    print(f"TOOL RAW RESULT: {result}")
                    tool_text = result.content[0].text
                    print(f"TOOL TEXT: {tool_text}")
                    # append tool response to conversation
                    conversation_contents.append(types.Content(role="tool", parts=[
                        types.Part.from_function_response(name=fc.name, response={"result": tool_text})
                    ]))
                    # ask model again with updated conversation
                    try:
                        response = client.models.generate_content(
                            model=model_id,
                            contents=conversation_contents,
                            config=types.GenerateContentConfig(tools=gemini_tools)
                        )
                    except Exception as e:
                        print(f"API call failed during conversation: {e}")
                        final_answer = f"(failed due to API error: {e})"
                        break
                    conversation_contents.append(response.candidates[0].content)
                    continue
                # no function call -> plain text answer
                # Gemini may put text in response.text or in parts
                if response.text:
                    final_answer = response.text
                elif response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    final_answer = getattr(part, 'text', str(part))
                else:
                    final_answer = "(no answer received)"
                break

            print(f"\nFinal AI Answer: {final_answer}")

if __name__ == "__main__":
    asyncio.run(main())