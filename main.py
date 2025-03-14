import requests
import unicodedata
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
# Track registered teams and draft readiness
global registered_teams
registered_teams = {}

global draft_ready
draft_ready = set()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Official 2025 Full-Time Drivers
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

# ✅ Store fantasy teams, draft order, and driver trades
fantasy_teams = {}
draft_order = []
draft_picks = {}
driver_trades = []

# ✅ Register a fantasy team
@app.get("/register_team")
def register_team(team_name: str):
    if team_name in registered_teams:
        return {"error": "Team name already registered"}
    
    registered_teams[team_name] = "Waiting to enter draft mode..."
    return {"message": f"{team_name} registered successfully!", "status": registered_teams[team_name]}

@app.get("/enter_draft_mode")
def enter_draft_mode(team_name: str):
    if team_name not in registered_teams:
        return {"error": "Team not registered"}

    draft_ready.add(team_name)
    registered_teams[team_name] = "Waiting for draft to start..."

    # If all 3 players are ready, start the draft automatically
    if len(draft_ready) == 3:
        return start_draft()

    return {"message": f"{team_name} entered draft mode!", "status": registered_teams[team_name]}

@app.get("/get_registered_teams")
def get_registered_teams():
    return {"teams": registered_teams}

# ✅ Start the snake draft
@app.get("/start_draft")
def start_draft():
    if len(fantasy_teams) < 3:
        raise HTTPException(status_code=400, detail="Need 3 teams to start draft!")

    global draft_picks
    draft_picks = {team: [] for team in draft_order}

    return {"message": "Draft started!", "draft_order": draft_order}

# ✅ Draft a driver (Snake Draft)
@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str):
    if team_name not in fantasy_teams:
        raise HTTPException(status_code=404, detail="Team not found!")
    
    if driver_name not in OFFICIAL_2025_DRIVERS:
        raise HTTPException(status_code=400, detail="Invalid driver!")

    if any(driver_name in picks for picks in draft_picks.values()):
        raise HTTPException(status_code=400, detail="Driver already drafted!")

    if len(draft_picks[team_name]) >= 6:
        raise HTTPException(status_code=400, detail="Team has already drafted 6 drivers!")

    draft_picks[team_name].append(driver_name)
    return {"message": f"{team_name} drafted {driver_name}!", "draft_picks": draft_picks}

# ✅ Allow teams to trade drivers
@app.post("/trade_driver")
def trade_driver(team1: str, team2: str, driver1: str, driver2: str, points: int = 0):
    if team1 not in fantasy_teams or team2 not in fantasy_teams:
        raise HTTPException(status_code=404, detail="One or both teams not found!")

    if driver1 not in draft_picks[team1] or driver2 not in draft_picks[team2]:
        raise HTTPException(status_code=400, detail="Invalid trade, drivers not owned!")

    # Swap drivers
    draft_picks[team1].remove(driver1)
    draft_picks[team2].remove(driver2)
    draft_picks[team1].append(driver2)
    draft_picks[team2].append(driver1)

    # Optional points trade
    if points > 0:
        driver_trades.append({"team1": team1, "team2": team2, "points": points})

    return {"message": "Trade completed!", "draft_picks": draft_picks}

# ✅ Mid-Season Redraft (After Race 12)
@app.get("/midseason_redraft")
def midseason_redraft():
    global draft_order
    global draft_picks  # Ensure this is defined BEFORE usage

    sorted_teams = sorted(draft_picks.keys(), key=lambda team: sum([0 for d in draft_picks[team]]))  
    draft_order = sorted_teams[::-1]  # Reverse order for last-place priority
    draft_picks = {team: [] for team in draft_order}  # Reset drafted teams

    return {"message": "Midseason redraft started!", "new_draft_order": draft_order}

# ✅ Check draft status
@app.get("/draft_status")
def draft_status():
    return {"draft_picks": draft_picks, "trades": driver_trades}