# MCP (Model Context Protocol) + Gemini AI + Vehicle API Integration

## 📋 Overview

This project demonstrates a three-tier architecture that connects:

1. **Google Gemini AI** - Language model that understands user queries and decides which tool to call
2. **MCP Server** - Protocol server that provides a growing toolkit (lookup, search, summary, and update)
3. **Data Source API** - REST API with vehicle information, now with search and update endpoints

The agent can now not only _read_ from the data source by ID but also **search vehicles by criteria**, **get inventory summaries**, and even **change a vehicle's status**, turning it into a more autonomous toolset.
The system works by having Gemini AI decide which tools to use, the MCP server bridges communication, and the data source provides the actual data.

---

## 🏗️ Architecture

```
┌─────────────────┐
│  User Query     │
│ (mcp_client.py) │
└────────┬────────┘
         │
         ├─────────────────────────────┐
         │                             │
    ┌────▼──────────────────────────┐  │
    │ Google Gemini AI              │  │
    │ (2.5-flash-lite model)        │  │
    │                               │  │
    │ - Understands user intent     │  │
    │ - Decides which tools to use  │  │
    │ - Generates final response    │  │
    └────┬──────────────────────────┘  │
         │                             │
         │ 1. Sends tools definitions  │
         │ 2. Gets back tool request   │
         │ 3. Sends tool result        │
         │ 4. Gets final answer        │
         │                             │
    ┌────▼──────────────────────────┐  │
    │ MCP Server (mcp_server.py)    │  │
    │                               │  │
    │ - Runs as subprocess          │  │
    │ - Exposes get_vehicle_details │  │
    │ - Communicates via stdio      │  │
    └────┬──────────────────────────┘  │
         │                             │
         │ HTTP GET Request            │
         │                             │
    ┌────▼──────────────────────────┐  │
    │ Data Source API (data_source) │  │
    │ (FastAPI on port 8001)        │  │
    │                               │  │
    │ - /vehicles/{vehicle_id}      │  │
    │ - /vehicles/search            │  │
    │ - PATCH /vehicles/{vehicle_id}│  │
    │ - Returns: make, model,       │  │
    │   status, destination         │  │
    └───────────────────────────────┘  │
         │                             │
         └─────────────────────────────┘
```

---

## 📂 File Breakdown

### 1. **data_source.py** - The Data Provider

**Purpose**: REST API that serves vehicle data  
**Framework**: FastAPI + Uvicorn  
**Port**: 8001

#### What it does:

- Provides a mock database of vehicles (101, 102, etc.)
- Exposes endpoints:
  - `GET /vehicles/{vehicle_id}` for direct lookup
  - `GET /vehicles/search` for criteria-based semantic search
  - `PATCH /vehicles/{vehicle_id}` to change status
- Returns JSON with: `make`, `model`, `status`, `destination`

#### Code Flow:

```python
VEHICLES = {
    "101": {"make": "Toyota", "model": "HiAce", ...},
    "102": {"make": "Honda", "model": "Fit", ...},
}

@app.get("/vehicles/{vehicle_id}")  # Endpoint
async def get_vehicle(vehicle_id: str):
    if vehicle_id not in VEHICLES:
        raise HTTPException(status_code=404, ...)
    return VEHICLES[vehicle_id]  # Returns vehicle data as JSON
```

#### To Run:

```bash
python data_source.py
# Server runs on http://127.0.0.1:8001
# Endpoints available:
#   GET /vehicles/{id}
#   GET /vehicles/search?status=Shipped&make=Toyota
#   PATCH /vehicles/{id}?status=In+Port
```

---

### 2. **mcp_server.py** - The Tool Provider

**Purpose**: MCP server that wraps the data source API as a tool  
**Framework**: FastMCP (built on top of MCP protocol)  
**Transport**: stdio (communicates via stdin/stdout)

#### What it does:

- Starts as a subprocess when mcp_client.py runs
- **Provides multiple tools**: `get_vehicle_details`, `search_vehicles`,
  `inventory_summary`, and `change_status`
- Fetches data from the data source API (localhost:8001)
- Converts HTTP responses into tool outputs with rich error messaging

#### Code Flow:

```python
@mcp.tool()  # Defines a callable tool
async def get_vehicle_details(vehicle_id: str) -> str:
    """Description of what this tool does"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{DATA_SOURCE_URL}/vehicles/{vehicle_id}")

        if response.status_code == 200:
            data = response.json()
            # Format result for Gemini
            return f"Vehicle {vehicle_id}: {data['make']} {data['model']} is currently {data['status']} heading to {data['destination']}."

        return f"Error: Could not find details for vehicle {vehicle_id}."

if __name__ == "__main__":
    mcp.run(transport="stdio")  # Communicates via stdin/stdout
```

#### Key Features:

- **Error Handling**: Tools return descriptive messages and suggestions when things fail
- **Timeout**: 5-second limit to prevent hanging
- **Schema**: Automatically generates input schema from function parameters
- **Agentic tools**:
  - `search_vehicles` acts as the agent's eyes when ID is unknown
  - `inventory_summary` supplies macro-level counts by status/destination
  - `change_status` allows the agent to perform write operations

#### To Run Manually (for testing):

```bash
python mcp_server.py
# Listens on stdin, outputs to stdout
```

---

### 3. **mcp_client.py** - The Orchestrator & Chain Manager

**Purpose**: Main application that coordinates between Gemini AI and MCP tools  
**Framework**: MCP Client SDK + Google Genai SDK

#### What it does:

1. Starts the MCP server as a subprocess
2. Connects to Gemini AI API
3. Gets available tools from MCP server (including new search/summary/update functions)
4. Sends tools to Gemini with a user query
5. Handles Gemini's tool requests in a **loop**, chaining multiple calls
6. Executes tools via MCP server and logs raw output for debugging
7. Sends results back to Gemini until a plain-text answer is produced
8. Handles API errors (e.g. quota limits) gracefully

#### Code Flow:

**Step 1: Initialize MCP Server Connection**

```python
server_params = StdioServerParameters(
    command="python",
    args=["mcp_server.py"]  # Start mcp_server.py as subprocess
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()  # Handshake with server
```

**Step 2: Get Available Tools**

```python
mcp_tools = await session.list_tools()  # Returns available tools from MCP server
# Result: [Tool(name="get_vehicle_details", description="...", inputSchema={...})]
```

**Step 3: Convert Tools for Gemini**

```python
gemini_tools = [
    types.Tool(
        function_declarations=[
            {
                "name": tool.name,                      # "get_vehicle_details"
                "description": tool.description,        # Tool description
                "parameters": clean_schema(tool.inputSchema),  # Input parameters
            } for tool in mcp_tools.tools
        ]
    )
]

# clean_schema() removes "additionalProperties" that Gemini doesn't support
```

Step 4: Send to Gemini with User Query (from CLI or prompt)

```python
user_query = "What is the status of vehicle 102?"  # example only; client now reads from command line or prompts the user

response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=user_query,
    config=types.GenerateContentConfig(tools=gemini_tools)
)

# Gemini analyzes: "User wants vehicle 102 info → I should call get_vehicle_details"
# (or "How many are shipped?" → call inventory_summary)
```

**Step 5: Handle Tool Request from Gemini (possibly multiple)**

```python
if response.candidates[0].content.parts[0].function_call:
    fc = response.candidates[0].content.parts[0].function_call
    # fc.name = "get_vehicle_details"
    # fc.args = {"vehicle_id": "102"}

    print(f"--- Gemini requested tool: {fc.name} with args {fc.args} ---")
```

**Step 6: Execute Tool via MCP Server**

```python
result = await session.call_tool(fc.name, fc.args)
# Sends to MCP server:
#   → MCP server calls get_vehicle_details("102")
#   → MCP server makes HTTP request to data_source
#   → Returns formatted result
```

**Step 7: Send Result Back to Gemini**

```python
final_response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=[
        types.Content(role="user", parts=[types.Part.from_text(text=user_query)]),
        response.candidates[0].content,  # Original Gemini response
        types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result.content[0].text}
                )
            ]
        )
    ],
    config=types.GenerateContentConfig(tools=gemini_tools)
)

# Gemini now has: "User asked → I called tool(s) → Tool returned data"
# Gemini generates final human-readable answer
```

**Step 8: Extract and Display Answer**

```python
answer = final_response.text
print(f"\nFinal AI Answer: {answer}")
# Example output: "Honda Fit is currently shipped heading to Kandy"
```

#### Key Helper Function:

```python
def clean_schema(schema):
    """Remove additionalProperties from schema as Gemini doesn't support it"""
    # Recursively removes "additionalProperties" from JSON schema
    # This is needed because MCP tools generate schemas with this field,
    # but Google Gemini API doesn't accept it
```

#### To Run:

```bash
# First, ensure data source is running in another terminal
python data_source.py

# Then in another terminal, run the client, supplying a query as arguments
python mcp_client.py "How many cars are in port?"

# or simply run without args and answer the prompt:
python mcp_client.py
# Enter your query: Find all Toyotas headed to Colombo

# You will see the available tools listed and then
# one or more tool calls. Example:
# --- Gemini requested tool: search_vehicles with args {'status': 'shipped'} ---
# --- Gemini requested tool: inventory_summary with args {} ---
# Final AI Answer: I found that there is 1 vehicle that has been shipped. Would you like to know its details?
```

---

## 🔄 Complete Message Flow

### Example: User asks "What is the status of vehicle 102?" (or "Find all Toyotas heading to Colombo")

```
User
  │
  └──> mcp_client.py
         │
         ├─ Starts mcp_server.py (as subprocess)
         │
         ├─ Connects to Google Gemini API
         │
         ├─ Gets tool list from MCP Server
         │  └─ [get_vehicle_details, search_vehicles, inventory_summary, change_status]
         │
         ├─ Sends to Gemini:
         │  "Here are available tools: [get_vehicle_details]
         │   User query: What is the status of vehicle 102?"
         │
         ├─ Gemini responds:
         │  "I should call get_vehicle_details with vehicle_id=102"
         │
         ├─ mcp_client calls MCP Server:
         │  "Execute get_vehicle_details({'vehicle_id': '102'})"
         │
         ├─ mcp_server.py receives call
         │  ├─ May call HTTP GET http://127.0.0.1:8001/vehicles/102
         │  ├─ Or GET http://127.0.0.1:8001/vehicles/search?status=Shipped
         │  └─ Or PATCH to update status
         │
         ├─ data_source.py responds:
         │  {"make": "Honda", "model": "Fit", "status": "Shipped", "destination": "Kandy"}
         │
         ├─ mcp_server returns formatted:
         │  "Vehicle 102: Honda Fit is currently Shipped heading to Kandy."
         │
         ├─ mcp_client gets result from MCP Server
         │
         ├─ Sends to Gemini:
         │  "Tool returned: Vehicle 102: Honda Fit is currently Shipped heading to Kandy."
         │
         ├─ Gemini generates final answer:
         │  "The Honda Fit (vehicle 102) is currently shipped and heading to Kandy."
│  (or "One vehicle is shipped; details: Vehicle 102 …")
         │
         └──> Final Answer displayed to user
```

---

## 🚀 Setup & Running

### Prerequisites

```bash
pip install fastapi uvicorn google-genai mcp fastmcp httpx python-dotenv
```

### Environment Variables

Create a `.env` file:

```
GOOGLE_API_KEY=your_actual_api_key_here
```

### Running Order (Important!)

**Terminal 1: Start Data Source API**

```bash
python data_source.py
# Output: INFO:     Uvicorn running on http://127.0.0.1:8001
```

**Terminal 2: Run MCP Client**

```bash
python mcp_client.py
# Output:
# --- Gemini requested tool: get_vehicle_details with args {'vehicle_id': '102'} ---
# Final AI Answer: ...
```

---

## 🔧 How Each Component Works

| Component          | Role          | Technology             | Communication           |
| ------------------ | ------------- | ---------------------- | ----------------------- |
| **data_source.py** | Data provider | FastAPI REST           | HTTP/JSON               |
| **mcp_server.py**  | Tool wrapper  | FastMCP                | stdio (stdin/stdout)    |
| **mcp_client.py**  | Orchestrator  | MCP Client + Genai SDK | Protocol buffers + HTTP |
| **Gemini API**     | AI Brain      | Google                 | HTTP REST API           |

---

## 🐛 Troubleshooting

### Issue: "Connection refused" on data source

**Solution**: Ensure `data_source.py` is running on port 8001

### Issue: "Gemini quota exceeded"

**Solution**: Use `gemini-2.5-flash-lite` instead of `gemini-2.0-flash` (better free quota)

### Issue: "invalid x-api-key"

**Solution**: Set `GOOGLE_API_KEY` environment variable with valid key

### Issue: Timeout errors

**Solution**: MCP server has 5-second timeout. Ensure data source responds within 5 seconds

---

## 📝 Key Concepts

1. **MCP (Model Context Protocol)**: Standard way to connect AI models with external tools
2. **Tool Definition**: Schema that describes input/output of a function
3. **Function Calling**: AI model decides to call a tool based on user query
4. **Tool Execution**: System executes the function and returns results
5. **Agentic Loop**: Cycle of reasoning → tool call → result → final answer

---

## 🎯 Customization

### Add More Tools

Edit `mcp_server.py`:

```python
@mcp.tool()
async def get_vehicle_location(vehicle_id: str) -> str:
    """Get current location of vehicle"""
    # Your implementation
    pass
```

### Change Queries

Edit `mcp_client.py`:

```python
# The script now reads the query from command-line args or a prompt.
# You can still modify this default placeholder if you like:
user_query = "What is the location of vehicle 102?"  # Change this
```

### Switch Models

Edit `mcp_client.py`:

```python
model_id = "gemini-2.5-pro"  # or any other available model
```

---

### ✅ Next steps

- Explore using **search_vehicles** for criteria-based lookups
- Ask the agent to **summarize inventory**: "How many cars are in port?"
- Use **change_status** to modify state programmatically

The README now reflects the latest toolset and agent capabilities.

---

## 📚 References

- [MCP Protocol Documentation](https://modelcontextprotocol.io)
- [Google Gemini API](https://ai.google.dev)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [FastMCP Python SDK](https://github.com/jlowin/fastmcp)

---

**Created**: 2026-02-25  
**Architecture**: Three-tier (AI + Protocol Bridge + Data API)  
**Status**: Working ✅
