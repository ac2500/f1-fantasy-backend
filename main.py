from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jolpica API endpoint for 2025 drivers (adjust if needed)
JOLPICA_DRIVERS_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"

# In-memory data
registered_teams = {}  # e.g. {"TeamName": ["Driver1", ...]}
fetched_drivers = []   # We'll store the 2025 driver names here once fetched

@app.on_event("startup")
def fetch_drivers_on_startup():
    """
    Automatically fetch the 2025 driver lineup from Jolpica
    when the FastAPI app starts.
    """
    global fetched_drivers
    try:
        resp = requests.get(JOLPICA_DRIVERS_URL, timeout=10)
        if resp.status_code != 200:
            print("⚠️ Could not fetch 2025 drivers from Jolpica. Using fallback.")
            fetched_drivers = fallback_driver_list()
            return
        
        data = resp.json()
        # This logic depends on how Jolpica structures the data:
        # For example, if data["MRData"]["DriverTable"]["Drivers"] has the 20 drivers:
        jolpica_drivers = data["MRData"]["DriverTable"]["Drivers"]
        
        # Extract name strings
        # e.g. "Max Verstappen", "Lewis Hamilton", etc.
        fetched_drivers = [
            f"{drv['givenName']} {drv['familyName']}"
            for drv in jolpica_drivers
        ]
        print(f"✅ Fetched {len(fetched_drivers)} drivers from Jolpica.")
    except Exception as e:
        print(f"⚠️ Exception fetching 2025 drivers: {e}")
        fetched_drivers = fallback_driver_list()

def fallback_driver_list():
    """
    Fallback if Jolpica is down or the 2025 endpoint fails.
    Return a known 20-driver list for 2025.
    """
    return [
        "Max Verstappen", "Liam Lawson",
        "Lando Norris", "Oscar Piastri",
        "Charles Leclerc", "Lewis Hamilton",
        "George Russell", "Andrea Kimi Antonelli",
        "Fernando Alonso", "Lance Stroll",
        "Pierre Gasly", "Jack Doohan",
        "Esteban Ocon", "Oliver Bearman",
        "Isack Hadjar", "Yuki Tsunoda",
        "Alexander Albon", "Carlos Sainz Jr.",
        "Nico Hulkenberg", "Gabriel Bortoleto"
    ]

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend Running with Jolpica 2025 drivers!"}

@app.get("/register_team")
def register_team(team_name: str):
    """Register a new team with an empty list of drivers."""
    global registered_teams
    if team_name in registered_teams:
        return {"error": "Team name already exists."}
    registered_teams[team_name] = []
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams():
    """Return the dict of teams and their drivers."""
    return {"teams": registered_teams}

@app.get("/get_available_drivers")
def get_available_drivers():
    """
    Return only drivers that haven't been drafted yet.
    Now using 'fetched_drivers' from Jolpica.
    """
    drafted = {driver for team_list in registered_teams.values() for driver in team_list}
    undrafted = [drv for drv in fetched_drivers if drv not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str):
    """Assign a driver to a team if not drafted yet and team has < 6 drivers."""
    global registered_teams
    # Basic checks
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team not found.")
    if driver_name not in fetched_drivers:
        raise HTTPException(status_code=400, detail="Invalid driver name (not in 2025 list).")

    # Check if driver is already drafted
    for drivers in registered_teams.values():
        if driver_name in drivers:
            raise HTTPException(status_code=400, detail="Driver already drafted.")

    # Check if team has 6 drivers
    if len(registered_teams[team_name]) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers!")

    registered_teams[team_name].append(driver_name)
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str):
    """Remove a driver from a team, returning them to the pool."""
    global registered_teams
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team not found.")
    if driver_name not in registered_teams[team_name]:
        raise HTTPException(status_code=400, detail="Driver not on this team.")

    registered_teams[team_name].remove(driver_name)
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams():
    """Clears all teams so we can start fresh."""
    global registered_teams
    registered_teams = {}
    return {"message": "All teams reset and drivers returned to pool!"}

# New route: Lock teams => create a new season ID
@app.post("/lock_teams")
def lock_teams():
    """
    Checks if we have exactly 3 teams with 6 drivers each,
    then locks them in a new 'season'.
    Returns a unique season_id for the front-end to load.
    """
    # Basic check
    if len(registered_teams) != 3:
        raise HTTPException(status_code=400, detail="We need exactly 3 teams to lock.")
    for t, drs in registered_teams.items():
        if len(drs) != 6:
            raise HTTPException(status_code=400, detail=f"Team {t} does not have 6 drivers yet.")

    season_id = str(uuid.uuid4())  # unique ID
    locked_seasons[season_id] = {
        "teams": {team: list(drs) for team, drs in registered_teams.items()},
        "points": {},  # for partial logic if needed
    }
    return {"season_id": season_id, "message": "Teams locked for 2025 season!"}

# New route: Retrieve locked season data
@app.get("/get_season")
def get_season(season_id: str):
    """
    Returns the locked teams + driver info + points for that season.
    """
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    return locked_seasons[season_id]

# Example partial logic: record driver points
@app.post("/update_driver_points")
def update_driver_points(season_id: str, driver_name: str, points: int):
    """
    Example route to add points to a driver for a locked season.
    The front-end can call this after each Grand Prix, ensuring
    no retroactive points if the driver wasn't on the team yet, etc.
    """
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    season_data = locked_seasons[season_id]

    # If needed, store partial logic like driver_join_time or only sum from time of joining.
    # For now, we'll just accumulate points in 'season_data["points"]'
    if driver_name not in season_data["points"]:
        season_data["points"][driver_name] = 0
    season_data["points"][driver_name] += points

    return {"message": f"Added {points} points to {driver_name} in season {season_id}."}