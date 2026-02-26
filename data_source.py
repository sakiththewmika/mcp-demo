from fastapi import FastAPI, HTTPException

app = FastAPI()

# Mock Database
VEHICLES = {
    "101": {"make": "Toyota", "model": "HiAce", "status": "In Port", "destination": "Colombo"},
    "102": {"make": "Honda", "model": "Fit", "status": "Shipped", "destination": "Kandy"},
    "103": {"make": "Ford", "model": "Transit", "status": "In Port", "destination": "Galle"},
    "104": {"make": "Tesla", "model": "Model X", "status": "Shipped", "destination": "Jaffna"},
    "105": {"make": "Nissan", "model": "NV200", "status": "In Port", "destination": "Trincomalee"},
}

@app.get("/vehicles")
async def list_vehicles():
    # Return a flat list suitable for inventory display
    return [{"id": vid, **details} for vid, details in VEHICLES.items()]

@app.get("/vehicles/search")
async def search_vehicles(make: str | None = None,
                          model: str | None = None,
                          status: str | None = None,
                          destination: str | None = None):
    """Search vehicles by optional criteria.

    Each query parameter is case-insensitive and will match if it appears anywhere
    in the corresponding vehicle field. When multiple parameters are provided the
    result is the intersection of all filters.
    """
    def match(value: str, term: str) -> bool:
        return term.lower() in value.lower()

    results = []
    for vid, info in VEHICLES.items():
        if make and not match(info.get("make", ""), make):
            continue
        if model and not match(info.get("model", ""), model):
            continue
        if status and not match(info.get("status", ""), status):
            continue
        if destination and not match(info.get("destination", ""), destination):
            continue
        results.append({"id": vid, **info})
    return results

@app.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str):
    if vehicle_id not in VEHICLES:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return VEHICLES[vehicle_id]
    """Search vehicles by optional criteria.

    Each query parameter is case-insensitive and will match if it appears anywhere
    in the corresponding vehicle field. When multiple parameters are provided the
    result is the intersection of all filters.
    """
    def match(value: str, term: str) -> bool:
        return term.lower() in value.lower()

    results = []
    for vid, info in VEHICLES.items():
        if make and not match(info.get("make", ""), make):
            continue
        if model and not match(info.get("model", ""), model):
            continue
        if status and not match(info.get("status", ""), status):
            continue
        if destination and not match(info.get("destination", ""), destination):
            continue
        results.append({"id": vid, **info})
    return results

@app.patch("/vehicles/{vehicle_id}")
async def update_vehicle_status(vehicle_id: str, status: str):
    """Update only the status field of a vehicle.  Raises 404 if not found."""
    if vehicle_id not in VEHICLES:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    VEHICLES[vehicle_id]["status"] = status
    return {"id": vehicle_id, **VEHICLES[vehicle_id]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)