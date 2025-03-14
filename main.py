from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Model for Drafting
class DraftRequest(BaseModel):
    team_name: str
    driver_name: str

# Pydantic Model for Undo Draft
class UndoRequest(BaseModel):
    team_name: str
    driver_name: str

# Global Data
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

@app.get("/get_all_drivers")
def get_all_drivers():
    """
    Return the full driver list so the frontend can show them all 
    (with strikethrough if drafted).
    """
    return {"drivers": all_drivers}

@app.get("/get_drafted_status")
def get_drafted_status():
    """
    Return which drivers are drafted by which team, so the frontend can
    apply strikethrough or remove dropdowns as needed.
    """
    return {"teams": registered_teams}

@app.post("/draft_driver")
def draft_driver(request: DraftRequest):
    """Assign a driver to a team if not drafted yet and team has < 6 drivers."""
    team_name = request.team_name
    driver_name = request.driver_name

    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team does not exist.")
    if driver_name not in all_drivers:
        raise HTTPException(status_code=400, detail="Invalid driver name.")

    # Check if driver is already drafted
    for t, drivers in registered_teams.items():
        if driver_name in drivers:
            raise HTTPException(status_code=400, detail="Driver already drafted!")

    # Check if team has 6 drivers already
    if len(registered_teams[team_name]) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers!")

    registered_teams[team_name].append(driver_name)
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(request: UndoRequest):
    """Remove a driver from a team, returning them to the available pool."""
    team_name = request.team_name
    driver_name = request.driver_name

    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team does not exist.")
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