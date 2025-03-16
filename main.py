from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid
from typing import List, Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URL for 2025 drivers from Jolpica (adjust if needed)
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"

# ---------- In-memory data for the DRAFT PHASE ----------
registered_teams = {}   # e.g. {"TeamA": ["Driver1", ...], "TeamB": [...], ...}
team_points = {}        # e.g. {"TeamA": 0, "TeamB": 0, ...}
fetched_drivers = []    # from Jolpica

# ---------- After locking: store a separate "locked season" ----------
locked_seasons = {}
# e.g. locked_seasons[season_id] = {
#   "teams": { "TeamA": [...], "TeamB": [...] },
#   "points": { "TeamA": 0, "TeamB": 0 },
#   "driver_points": { "DriverName": 0 },  # if you track per-driver points
# }

# =========== 1) Jolpica fetch on startup ===========
@app.on_event("startup")
def fetch_2025_drivers_on_startup():
    global fetched_drivers
    try:
        resp = requests.get(JOLPICA_2025_URL, timeout=10)
        if resp.status_code != 200:
            print("⚠️ Could not fetch 2025 drivers from Jolpica. Using fallback.")
            fetched_drivers = fallback_2025_driver_list()
            return
        data = resp.json()
        jolpica_drivers = data["MRData"]["DriverTable"]["Drivers"]
        fetched_drivers = [
            f"{drv['givenName']} {drv['familyName']}"
            for drv in jolpica_drivers
        ]
        print(f"✅ Fetched {len(fetched_drivers)} drivers from Jolpica.")
    except Exception as e:
        print(f"⚠️ Exception fetching Jolpica 2025 drivers: {e}")
        fetched_drivers = fallback_2025_driver_list()

def fallback_2025_driver_list():
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
    return {"message": "F1 Fantasy Backend with 2-sided sweetener trades in locked season."}

# =========== 2) Draft Phase Endpoints ===========

@app.get("/register_team")
def register_team(team_name: str):
    global registered_teams, team_points
    if team_name in registered_teams:
        return {"error": "Team name already exists."}
    registered_teams[team_name] = []
    team_points[team_name] = 0
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams():
    return {"teams": registered_teams}

@app.get("/get_team_points")
def get_team_points():
    return {"team_points": team_points}

@app.get("/get_available_drivers")
def get_available_drivers():
    drafted = {drv for roster in registered_teams.values() for drv in roster}
    undrafted = [drv for drv in fetched_drivers if drv not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str):
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team not found.")
    if driver_name not in fetched_drivers:
        raise HTTPException(status_code=400, detail="Invalid driver name.")

    for drs in registered_teams.values():
        if driver_name in drs:
            raise HTTPException(status_code=400, detail="Driver already drafted.")
    if len(registered_teams[team_name]) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers!")

    registered_teams[team_name].append(driver_name)
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str):
    if team_name not in registered_teams:
        raise HTTPException(status_code=404, detail="Team not found.")
    if driver_name not in registered_teams[team_name]:
        raise HTTPException(status_code=400, detail="Driver not on this team.")

    registered_teams[team_name].remove(driver_name)
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams():
    global registered_teams, team_points
    registered_teams = {}
    team_points = {}
    return {"message": "All teams reset and drivers returned to pool!"}

# =========== 3) Lock Teams => create a locked season ===========

@app.post("/lock_teams")
def lock_teams():
    if len(registered_teams) != 3:
        raise HTTPException(status_code=400, detail="We need exactly 3 teams to lock.")
    for t, drs in registered_teams.items():
        if len(drs) != 6:
            raise HTTPException(status_code=400, detail=f"Team {t} does not have 6 drivers yet.")

    season_id = str(uuid.uuid4())
    locked_seasons[season_id] = {
        "teams": {team: list(registered_teams[team]) for team in registered_teams},
        "points": {team: team_points[team] for team in team_points},
        # optional: "driver_points": {} if you want to track driver-specific
    }
    return {"message": "Teams locked for 2025 season!", "season_id": season_id}

@app.get("/get_season")
def get_season(season_id: str):
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    return locked_seasons[season_id]

# =========== 4) Balanced Trade in Locked Season (2-sided sweetener) ===========

from pydantic import BaseModel

class LockedTradeRequest(BaseModel):
    from_team: str
    to_team: str
    drivers_from_team: List[str]
    drivers_to_team: List[str]
    # two-sided sweetener
    from_team_points: int = 0  # points from from_team to to_team
    to_team_points: int = 0    # points from to_team to from_team

@app.post("/trade_locked")
def trade_locked(season_id: str, request: LockedTradeRequest):
    """
    Balanced trade in the locked environment. Both teams remain at 6 drivers.
    from_team can pay from_team_points to to_team, or to_team can pay to_team_points to from_team,
    or both.
    """
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")

    season_data = locked_seasons[season_id]
    locked_teams = season_data["teams"]
    locked_points = season_data["points"]

    # 1. Validate teams
    if request.from_team not in locked_teams or request.to_team not in locked_teams:
        raise HTTPException(status_code=404, detail="One or both teams not found in this season.")

    from_roster = locked_teams[request.from_team]
    to_roster = locked_teams[request.to_team]

    # 2. Validate driver ownership
    for drv in request.drivers_from_team:
        if drv not in from_roster:
            raise HTTPException(status_code=400, detail=f"{request.from_team} does not own {drv}")
    for drv in request.drivers_to_team:
        if drv not in to_roster:
            raise HTTPException(status_code=400, detail=f"{request.to_team} does not own {drv}")

    # 3. Balanced driver swap: same # of drivers each way
    x = len(request.drivers_from_team)
    y = len(request.drivers_to_team)
    if x != y:
        raise HTTPException(status_code=400, detail="Trade must have same # of drivers each way.")

    # 4. Ensure rosters remain 6
    # from_team has 6 => after removing x, adding y => must remain 6 => y = x
    # to_team similarly

    # 5. Validate sweetener from from_team
    if request.from_team_points < 0:
        raise HTTPException(status_code=400, detail="from_team_points cannot be negative.")
    if request.from_team_points > locked_points.get(request.from_team, 0):
        raise HTTPException(
            status_code=400,
            detail=f"{request.from_team} does not have enough points to pay {request.from_team_points}."
        )

    # Validate sweetener from to_team
    if request.to_team_points < 0:
        raise HTTPException(status_code=400, detail="to_team_points cannot be negative.")
    if request.to_team_points > locked_points.get(request.to_team, 0):
        raise HTTPException(
            status_code=400,
            detail=f"{request.to_team} does not have enough points to pay {request.to_team_points}."
        )

    # 6. Remove drivers
    for drv in request.drivers_from_team:
        from_roster.remove(drv)
    for drv in request.drivers_to_team:
        to_roster.remove(drv)

    # 7. Add them to the other side
    from_roster.extend(request.drivers_to_team)
    to_roster.extend(request.drivers_from_team)

    # 8. Transfer sweetener points
    # from_team -> to_team
    locked_points[request.from_team] -= request.from_team_points
    locked_points[request.to_team] += request.from_team_points

    # to_team -> from_team
    locked_points[request.to_team] -= request.to_team_points
    locked_points[request.from_team] += request.to_team_points

    return {
        "message": "Locked season trade completed!",
        "season_id": season_id,
        "from_team": {
            "name": request.from_team,
            "roster": from_roster,
            "points": locked_points[request.from_team]
        },
        "to_team": {
            "name": request.to_team,
            "roster": to_roster,
            "points": locked_points[request.to_team]
        }
    }