import requests
import unicodedata
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

# ✅ Official 2025 Full-Time Drivers (Manually Verified)
OFFICIAL_2025_DRIVERS = [
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
]

# ✅ Normalize names to avoid formatting mismatches
def normalize_name(name):
    return unicodedata.normalize("NFKD", name).lower().strip()

# ✅ Fetch live drivers from Jolpica API
def get_live_drivers():
    url = "https://api.jolpi.ca/ergast/f1/current/drivers.json"
    response = requests.get(url)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch driver data")

    data = response.json()
    all_drivers = data["MRData"]["DriverTable"]["Drivers"]

    # ✅ Ensure we **only** return 2025 full-time drivers
    filtered_drivers = [
        f"{driver['givenName']} {driver['familyName']}"
        for driver in all_drivers
        if normalize_name(f"{driver['givenName']} {driver['familyName']}") in 
           [normalize_name(name) for name in OFFICIAL_2025_DRIVERS]
    ]

    # ✅ Hardcoded fallback if fewer than 20 drivers appear
    if len(filtered_drivers) != 20:
        return OFFICIAL_2025_DRIVERS

    return filtered_drivers

# ✅ Fetch real-time driver standings, handling missing data
def get_driver_points():
    url = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
    response = requests.get(url)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch driver standings")

    data = response.json()

    # ✅ Debugging: Print full API response
    print("Driver Standings API Response:", data)

    # ✅ Handle case where standings might be missing
    standings = data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])

    if not standings or len(standings) == 0:
        print("⚠️ No standings data available!")
        return {driver: 0 for driver in OFFICIAL_2025_DRIVERS}  # Default to 0 points

    # ✅ Extract driver points from standings
    driver_points = {
        f"{entry['Driver']['givenName']} {entry['Driver']['familyName']}": int(entry.get("points", 0))
        for entry in standings[0]["DriverStandings"]
    }

    return driver_points

# ✅ API endpoint to return **only full-time 2025 F1 drivers**
@app.get("/available_drivers")
def fetch_drivers():
    try:
        drivers = get_live_drivers()
        return {"drivers": drivers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ API endpoint to return real-time F1 driver standings
@app.get("/driver_standings")
def fetch_driver_standings():
    try:
        return get_driver_points()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ Updated function: Teams now show **real-time** driver points
@app.get("/teams")
def get_teams():
    try:
        drivers = get_live_drivers()  # Fetch real-time drivers
        driver_points = get_driver_points()  # Fetch real-time points

        # ✅ Assign drivers & update points dynamically
        teams = {
            "Red Bull Racing": {
                "drivers": ["Max Verstappen", "Liam Lawson"],
                "points": sum(driver_points.get(d, 0) for d in ["Max Verstappen", "Liam Lawson"])
            },
            "McLaren": {
                "drivers": ["Lando Norris", "Oscar Piastri"],
                "points": sum(driver_points.get(d, 0) for d in ["Lando Norris", "Oscar Piastri"])
            },
            "Ferrari": {
                "drivers": ["Charles Leclerc", "Lewis Hamilton"],
                "points": sum(driver_points.get(d, 0) for d in ["Charles Leclerc", "Lewis Hamilton"])
            },
            "Mercedes": {
                "drivers": ["George Russell", "Andrea Kimi Antonelli"],
                "points": sum(driver_points.get(d, 0) for d in ["George Russell", "Andrea Kimi Antonelli"])
            },
            "Aston Martin": {
                "drivers": ["Fernando Alonso", "Lance Stroll"],
                "points": sum(driver_points.get(d, 0) for d in ["Fernando Alonso", "Lance Stroll"])
            },
            "Alpine": {
                "drivers": ["Pierre Gasly", "Jack Doohan"],
                "points": sum(driver_points.get(d, 0) for d in ["Pierre Gasly", "Jack Doohan"])
            },
            "Haas": {
                "drivers": ["Esteban Ocon", "Oliver Bearman"],
                "points": sum(driver_points.get(d, 0) for d in ["Esteban Ocon", "Oliver Bearman"])
            },
            "Racing Bulls": {
                "drivers": ["Isack Hadjar", "Yuki Tsunoda"],
                "points": sum(driver_points.get(d, 0) for d in ["Isack Hadjar", "Yuki Tsunoda"])
            },
            "Williams": {
                "drivers": ["Alexander Albon", "Carlos Sainz Jr."],
                "points": sum(driver_points.get(d, 0) for d in ["Alexander Albon", "Carlos Sainz Jr."])
            },
            "Kick Sauber": {
                "drivers": ["Nico Hülkenberg", "Gabriel Bortoleto"],
                "points": sum(driver_points.get(d, 0) for d in ["Nico Hülkenberg", "Gabriel Bortoleto"])
            },
        }

        return {"teams": teams}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))