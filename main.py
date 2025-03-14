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

# Global Data
registered_teams = {}   # e.g., { "TeamName": ["Driver1", "Driver2"], ... }
available_drivers = [
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
    """Registers a new team with an empty list of drivers."""
    global registered_teams
    if team_name in registered_teams:
        return {"error": "Team name already registered."}

    registered_teams[team_name] = []
    return {"message": f"{team_name} registered successfully!", "teams": registered_teams}

@app.get("/get_registered_teams")
def get_registered_teams():
    """Returns all registered teams and their drafted drivers."""
    return {"teams": registered_teams}

@app.get("/get_available_drivers")
def get_available_drivers():
    """Returns the list of drivers who haven't been drafted yet."""
    drafted = {driver for team_drivers in registered_teams.values() for driver in team_drivers}
    undrafted = [driver for driver in available_drivers if driver not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str):
    """Assign a driver to a team if not already drafted."""
    global registered_teams
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team does not exist.")

    if driver_name not in available_drivers:
        raise HTTPException(status_code=400, detail="Invalid driver name.")

    # Check if driver is already drafted
    for team, drivers in registered_teams.items():
        if driver_name in drivers:
            raise HTTPException(status_code=400, detail="Driver already drafted.")

    registered_teams[team_name].append(driver_name)
    return {"message": f"{driver_name} drafted by {team_name}!", "teams": registered_teams}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str):
    """Remove a driver from a team and return them to the pool."""
    global registered_teams
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team does not exist.")

    if driver_name not in registered_teams[team_name]:
        raise HTTPException(status_code=400, detail="Driver not on this team.")

    registered_teams[team_name].remove(driver_name)
    return {"message": f"{driver_name} returned to the pool from {team_name}.", "teams": registered_teams}