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
    "Alexander Albon", "Carlos Sainz Jr.",  # ✅ Ensure Carlos Sainz is included
    "Nico Hülkenberg", "Gabriel Bortoleto"
]

# ✅ Function to normalize names for better matching
def normalize_name(name):
    return unicodedata.normalize("NFKD", name).lower().strip()

# ✅ Updated function to fetch drivers
def get_live_drivers():
    url = "https://api.jolpi.ca/ergast/f1/current/drivers.json"
    response = requests.get(url)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch driver data")

    data = response.json()
    all_drivers = data["MRData"]["DriverTable"]["Drivers"]

    # ✅ Convert API driver names to lowercase & compare against normalized official list
    filtered_drivers = [
        f"{driver['givenName']} {driver['familyName']}"
        for driver in all_drivers
        if normalize_name(f"{driver['givenName']} {driver['familyName']}") in 
           [normalize_name(name) for name in OFFICIAL_2025_DRIVERS]
    ]

    # ✅ Debugging Print (Remove this after testing)
    print("API Drivers:", [f"{d['givenName']} {d['familyName']}" for d in all_drivers])
    print("Filtered Drivers:", filtered_drivers)

    # ✅ Hardcoded fallback if fewer than 20 drivers appear
    if len(filtered_drivers) != 20:
        return OFFICIAL_2025_DRIVERS

    return filtered_drivers

# ✅ API endpoint to return **only full-time 2025 F1 drivers**
@app.get("/available_drivers")
def fetch_drivers():
    try:
        drivers = get_live_drivers()
        return {"drivers": drivers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))