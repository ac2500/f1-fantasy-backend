from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models for JSON requests
class AssignRequest(BaseModel):
    team_name: str
    driver_name: str

class UndoRequest(BaseModel):
    team_name: str

# Global data
registered_teams = {}  # e.g. { "TeamName": "Waiting..." or "Drafting..." }
draft_picks = {}       # e.g. { "TeamName": ["Driver1", "Driver2"] }
available_drivers = ["Driver 1", "Driver 2", "Driver 3"]  # Example drivers

# Register a team
@app.get("/register_team")
def register_team(team_name: str):
    global registered_teams, draft_picks
    if team_name in registered_teams:
        return {"error": "Team name already registered"}
    
    registered_teams[team_name] = "Waiting..."
    draft_picks[team_name] = []
    return {"message": f"{team_name} registered successfully!"}

# Get the teams + status
@app.get("/get_registered_teams")
def get_registered_teams():
    global registered_teams, draft_picks
    # Return a structure with each team's status and picks
    # Example: { "teams": { "TeamA": ["Driver1", "Driver2"], "TeamB": [] } }
    result = {}
    for team in draft_picks:
        result[team] = draft_picks[team]
    return {"teams": result}

# Get the list of available drivers
@app.get("/get_available_drivers")
def get_available_drivers():
    global available_drivers, draft_picks
    # Remove drivers already drafted
    drafted = set()
    for picks in draft_picks.values():
        for driver in picks:
            drafted.add(driver)
    undrafted = [d for d in available_drivers if d not in drafted]
    return {"drivers": undrafted}

# Assign driver to a team (POST with JSON)
@app.post("/assign_driver")
def assign_driver(request: AssignRequest):
    global draft_picks, available_drivers
    team_name = request.team_name
    driver_name = request.driver_name

    if team_name not in draft_picks:
        raise HTTPException(status_code=404, detail="Team not found!")
    if driver_name not in available_drivers:
        raise HTTPException(status_code=400, detail="Invalid driver!")

    # Check if driver is already drafted
    for picks in draft_picks.values():
        if driver_name in picks:
            raise HTTPException(status_code=400, detail="Driver already drafted!")

    draft_picks[team_name].append(driver_name)
    return {"message": f"{driver_name} assigned to {team_name}"}

# Undo the last driver pick from a team (POST with JSON)
@app.post("/undo_draft")
def undo_draft(request: UndoRequest):
    global draft_picks
    team_name = request.team_name

    if team_name not in draft_picks or not draft_picks[team_name]:
        return {"error": "No driver drafted for this team"}

    driver_name = draft_picks[team_name].pop()  # Remove last pick
    return {"message": f"{driver_name} removed from {team_name}!"}