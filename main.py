from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root route to check if backend is running
@app.get("/")
def read_root():
    return {"message": "F1 Fantasy Backend is Running!"}

# ✅ Add this endpoint to send team data to the frontend
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fetch live F1 drivers from Ergast API
def get_live_drivers():
    url = "https://ergast.com/api/f1/current/drivers.json"
    response = requests.get(url)
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch driver data")

    data = response.json()
    drivers = [
        f"{driver['givenName']} {driver['familyName']}"
        for driver in data["MRData"]["DriverTable"]["Drivers"]
    ]
    return drivers

# ✅ Get available drivers dynamically
@app.get("/available_drivers")
def fetch_drivers():
    try:
        drivers = get_live_drivers()
        return {"drivers": drivers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))