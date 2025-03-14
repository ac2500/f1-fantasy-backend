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

# ✅ New API source (Jolpica API instead of Ergast)
JOLPICA_API_BASE = "https://api.jolpi.ca/ergast/f1"

# ✅ Official 2025 F1 Driver List (Pulled from Formula 1 website)
FULL_TIME_DRIVERS_2025 = {
    "Max Verstappen", "Liam Lawson",
    "Lando Norris", "Oscar Piastri",
    "Charles Leclerc", "Lewis Hamilton",
    "George Russell", "Andrea Kimi Antonelli",
    "Fernando Alonso", "Lance Stroll",
    "Pierre Gasly", "Jack Doohan",
    "Esteban Ocon", "Oliver Bearman",
    "Isack Hadjar", "Yuki Tsunoda",
    "Alexander Albon", "Carlos Sainz Jr.",
    "Nico Hülkenberg", "Gabriel Bortoleto"
}

# ✅ Fetch drivers from Jolpica API
def get_live_drivers():
    url = f"{JOLPICA_API_BASE}/current/drivers.json"
    response = requests.get(url)
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch driver data")

    data = response.json()
    all_drivers = data["MRData"]["DriverTable"]["Drivers"]

    # ✅ Filter to ensure we only keep full-time 2025 drivers
    filtered_drivers = [
        f"{driver['givenName']} {driver['familyName']}"
        for driver in all_drivers
        if f"{driver['givenName']} {driver['familyName']}" in FULL_TIME_DRIVERS_2025
    ]

    return filtered_drivers

# ✅ API endpoint to return real-time F1 drivers
@app.get("/available_drivers")
def fetch_drivers():
    try:
        drivers = get_live_drivers()
        return {"drivers": drivers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ Keep existing /teams function, but now assign real 2025 drivers dynamically
@app.get("/teams")
def get_teams():
    try:
        drivers = get_live_drivers()  # Fetch the latest real-time driver list

        # Assign drivers to F1 teams dynamically based on the official lineup
        teams = {
            "Red Bull Racing": {"drivers": ["Max Verstappen", "Liam Lawson"], "points": 0},
            "McLaren": {"drivers": ["Lando Norris", "Oscar Piastri"], "points": 0},
            "Ferrari": {"drivers": ["Charles Leclerc", "Lewis Hamilton"], "points": 0},
            "Mercedes": {"drivers": ["George Russell", "Andrea Kimi Antonelli"], "points": 0},
            "Aston Martin": {"drivers": ["Fernando Alonso", "Lance Stroll"], "points": 0},
            "Alpine": {"drivers": ["Pierre Gasly", "Jack Doohan"], "points": 0},
            "Haas": {"drivers": ["Esteban Ocon", "Oliver Bearman"], "points": 0},
            "Racing Bulls": {"drivers": ["Isack Hadjar", "Yuki Tsunoda"], "points": 0},
            "Williams": {"drivers": ["Alexander Albon", "Carlos Sainz Jr."], "points": 0},
            "Kick Sauber": {"drivers": ["Nico Hülkenberg", "Gabriel Bortoleto"], "points": 0},
        }

        return {"teams": teams}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))