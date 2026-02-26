import httpx
from fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP("VehicleExportServer")

DATA_SOURCE_URL = "http://127.0.0.1:8001" # Or localhost:8001

@mcp.tool()
async def get_vehicle_details(vehicle_id: str) -> str:
    """Retrieve a single vehicle's current information using its unique ID.

    This is the **precise lookup** tool. Use it when you already know the
    vehicle's identifier. If the ID does not exist, the tool returns a clear
    message so the upstream agent can decide to search or try another ID.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{DATA_SOURCE_URL}/vehicles/{vehicle_id}")
            if response.status_code == 200:
                data = response.json()
                return f"Vehicle {vehicle_id}: {data['make']} {data['model']} is currently {data['status']} heading to {data['destination']}."
            # explicit not found case
            if response.status_code == 404:
                # attempt to help by listing nearby ids
                vehicles = await list_vehicles_internal()
                close = ", ".join(v['id'] for v in vehicles[:3])
                return f"Error: Vehicle {vehicle_id} not found. Nearby IDs: {close}"
            return f"Error: Could not find details for vehicle {vehicle_id}."
    except httpx.TimeoutException:
        return f"Error: Request to data source timed out for vehicle {vehicle_id}. Ensure the server at {DATA_SOURCE_URL} is running."
    except Exception as e:
        return f"Error: Could not fetch details for vehicle {vehicle_id}: {str(e)}"

# internal helper to avoid repeating the same http call
async def list_vehicles_internal():
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{DATA_SOURCE_URL}/vehicles")
        if response.status_code == 200:
            return response.json()
        return []

@mcp.tool()
async def list_vehicles() -> str:
    """Return every vehicle currently stored, one per line.

    This is a **broad inspection** tool. Avoid using it when you only need
    counts or a particular item, since large inventories would be cumbersome
    for an agent to consume. Prefer `inventory_summary` or `search_vehicles`
    for more targeted queries.
    """
    try:
        vehicles = await list_vehicles_internal()
        if vehicles:
            return "\n".join([
                f"Vehicle {v['id']}: {v['make']} {v['model']} is currently {v['status']} heading to {v['destination']}"
                for v in vehicles
            ])
        return "Error: Could not retrieve vehicle list."
    except httpx.TimeoutException:
        return f"Error: Request to data source timed out. Ensure the server at {DATA_SOURCE_URL} is running."
    except Exception as e:
        return f"Error: Could not fetch vehicle list: {str(e)}"

# --- new smart agent tools ---

@mcp.tool()
async def search_vehicles(make: str | None = None,
                          model: str | None = None,
                          status: str | None = None,
                          destination: str | None = None) -> str:
    """Find vehicles matching one or more criteria without knowing the ID.

    Provide any combination of make, model, status or destination. The search
    is case-insensitive and will return vehicles where the field contains the
    given term. This tool is the agent's "eyes" when it is uncertain about
    exact identifiers. If no results are found, the response explains and may
    offer suggestions to broaden the query.
    """
    try:
        params = {}
        if make:
            params['make'] = make
        if model:
            params['model'] = model
        if status:
            params['status'] = status
        if destination:
            params['destination'] = destination
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{DATA_SOURCE_URL}/vehicles/search", params=params)
            if response.status_code == 200:
                hits = response.json()
                if not hits:
                    return ("No vehicles matched your criteria. "
                            "Try relaxing one of the filters or check spelling.")
                return "\n".join([
                    f"Vehicle {v['id']}: {v['make']} {v['model']} is {v['status']} heading to {v['destination']}"
                    for v in hits
                ])
            return "Error: search endpoint returned unexpected status."
    except httpx.TimeoutException:
        return "Error: timeout while searching vehicles."
    except Exception as e:
        return f"Error during search: {e}"

@mcp.tool()
async def inventory_summary() -> str:
    """Provide a condensed overview of the current fleet.

    Returns counts by status and destination. This gives the agent a macro view
    of the inventory so it can answer questions like "How many cars are in port?"
    without iterating over every record. Use this before launching wide queries.
    """
    try:
        vehicles = await list_vehicles_internal()
        if not vehicles:
            return "Inventory is empty."
        status_counts = {}
        destination_counts = {}
        for v in vehicles:
            status_counts[v['status']] = status_counts.get(v['status'], 0) + 1
            destination_counts[v['destination']] = destination_counts.get(v['destination'], 0) + 1
        status_lines = [f"{k}: {c}" for k, c in status_counts.items()]
        dest_lines = [f"{k}: {c}" for k, c in destination_counts.items()]
        return (
            "Status counts:\n" + "\n".join(status_lines) +
            "\nDestination counts:\n" + "\n".join(dest_lines)
        )
    except Exception as e:
        return f"Error generating inventory summary: {e}"

@mcp.tool()
async def change_status(vehicle_id: str, new_status: str) -> str:
    """Update the status of a vehicle identified by ID.

    This tool grants the agent write access. It should be invoked after the
    correct vehicle is determined (e.g. via `search_vehicles` or
    `get_vehicle_details`). Returns the updated record or a meaningful error.
    If the ID does not exist, the response suggests similar available IDs.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.patch(
                f"{DATA_SOURCE_URL}/vehicles/{vehicle_id}", params={'status': new_status}
            )
            if response.status_code == 200:
                data = response.json()
                return f"Updated vehicle {vehicle_id} status to {data['status']}."
            if response.status_code == 404:
                vehicles = await list_vehicles_internal()
                suggestions = ", ".join(v['id'] for v in vehicles[:3])
                return (f"Error: Vehicle {vehicle_id} not found. "
                        f"Available IDs include {suggestions}.")
            return f"Error: could not change status ({response.status_code})."
    except httpx.TimeoutException:
        return "Error: timeout while attempting to change status."
    except Exception as e:
        return f"Error updating status: {e}"

if __name__ == "__main__":
    mcp.run(transport="sse", host="127.0.0.1", port=8000)