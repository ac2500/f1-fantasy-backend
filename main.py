from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data
registered_teams = {}  # e.g. { "TeamName": ["Driver1", ... up to 6], ... }

all_drivers = [
    "Max Verstappen", "Lewis Hamilton", "Charles Leclerc", "Lando Norris", "Sergio Perez",
    "George Russell", "Carlos Sainz", "Oscar Piastri", "Fernando Alonso", "Pierre Gasly",
    "Esteban Ocon", "Lance Stroll", "Yuki Tsunoda", "Kevin Magnussen", "Nico Hulkenberg",
    "Alexander Albon", "Logan Sargeant", "Zhou Guanyu", "Valtteri Bottas"
]

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend Running!"}

@app.get("/register_team")
def register_team(team_name: str):
    """
    Register a new team with an empty list of drivers.
    """
    global registered_teams
    if team_name in registered_teams:
        return {"error": "Team name already exists."}
    registered_teams[team_name] = []
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams():
    """
    Return the dict of teams and their drivers.
    """
    return {"teams": registered_teams}

@app.get("/get_available_drivers")
def get_available_drivers():
    """
    Return only drivers that haven't been drafted yet.
    """
    drafted = {driver for team_list in registered_teams.values() for driver in team_list}
    undrafted = [drv for drv in all_drivers if drv not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str):
    """
    Assign a driver to a team if not drafted yet and team has < 6 drivers.
    Uses query params in a POST request.
    """
    global registered_teams
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team not found.")
    if driver_name not in all_drivers:
        raise HTTPException(status_code=400, detail="Invalid driver name.")

    # Check if driver is already drafted
    for t, drivers in registered_teams.items():
        if driver_name in drivers:
            raise HTTPException(status_code=400, detail="Driver already drafted!")

    # Check if team has 6 drivers
    if len(registered_teams[team_name]) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers!")

    registered_teams[team_name].append(driver_name)
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str):
    """
    Remove a driver from a team, returning them to the pool.
    """
    global registered_teams
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team not found.")
    if driver_name not in registered_teams[team_name]:
        raise HTTPException(status_code=400, detail="Driver not on this team.")

    registered_teams[team_name].remove(driver_name)
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams():
    """
    Clears all teams so we can start fresh.
    """
    global registered_teams
    registered_teams = {}
    return {"message": "All teams reset and drivers returned to pool!"}

# New route: Lock teams
@app.post("/lock_teams")
def lock_teams():
    """
    Ensures exactly 3 teams exist, each with 6 drivers.
    Returns a success message if valid.
    """
    if len(registered_teams) != 3:
        raise HTTPException(status_code=400, detail="We need exactly 3 teams to lock.")

    for t, drs in registered_teams.items():
        if len(drs) != 6:
            raise HTTPException(
                status_code=400,
                detail=f"Team {t} does not have 6 drivers yet. Current count: {len(drs)}"
            )

    return {"message": "Teams locked for 2025 season!"}