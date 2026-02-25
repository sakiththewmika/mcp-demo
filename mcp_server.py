import httpx
from fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP("VehicleExportServer")

DATA_SOURCE_URL = "http://127.0.0.1:8001" # Or localhost:8001

@mcp.tool()
async def get_vehicle_details(vehicle_id: str) -> str:
    """Fetches real-time status and details for a specific vehicle by its ID."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{DATA_SOURCE_URL}/vehicles/{vehicle_id}")
            if response.status_code == 200:
                data = response.json()
                return f"Vehicle {vehicle_id}: {data['make']} {data['model']} is currently {data['status']} heading to {data['destination']}."
            return f"Error: Could not find details for vehicle {vehicle_id}."
    except httpx.TimeoutException:
        return f"Error: Request to data source timed out for vehicle {vehicle_id}. Ensure the server at {DATA_SOURCE_URL} is running."
    except Exception as e:
        return f"Error: Could not fetch details for vehicle {vehicle_id}: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")