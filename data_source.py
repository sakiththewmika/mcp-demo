from fastapi import FastAPI, HTTPException

app = FastAPI()

# Mock Database
VEHICLES = {
    "101": {"make": "Toyota", "model": "HiAce", "status": "In Port", "destination": "Colombo"},
    "102": {"make": "Honda", "model": "Fit", "status": "Shipped", "destination": "Kandy"},
}

@app.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str):
    if vehicle_id not in VEHICLES:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return VEHICLES[vehicle_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)