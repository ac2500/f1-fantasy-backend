from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid
from typing import List
from datetime import datetime
import json
import logging

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models

# Create database tables if they do not exist.
# (Make sure you are not dropping tables on startup.)
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to provide a database session.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Global variable for draft-phase driver list (fetched from Jolpica).
# This is acceptable for the draft phase; once the season is locked, all critical data is stored in the database.
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"
fetched_drivers = []

@app.on_event("startup")
def fetch_2025_drivers_on_startup():
    global fetched_drivers
    try:
        resp = requests.get(JOLPICA_2025_URL, timeout=10)
        if resp.status_code != 200:
            print("⚠️ Could not fetch drivers from Jolpica. Using fallback.")
            fetched_drivers = fallback_2025_driver_list()
            return
        data = resp.json()
        jolpica_drivers = data["MRData"]["DriverTable"]["Drivers"]
        fetched_drivers = [f"{drv['givenName']} {drv['familyName']}" for drv in jolpica_drivers]
        print(f"✅ Fetched {len(fetched_drivers)} drivers from Jolpica.")
    except Exception as e:
        print(f"⚠️ Exception fetching drivers: {e}")
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
    return {"message": "F1 Fantasy Backend with persistent data on Neon."}

# ---------- Draft Phase Endpoints (For registering teams, drafting drivers, etc.) ----------

@app.get("/register_team")
def register_team(team_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if team:
        return {"error": "Team name already exists."}
    new_team = models.Team(name=team_name, roster=json.dumps([]), points=0)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    result = {team.name: json.loads(team.roster) for team in teams}
    return {"teams": result}

@app.get("/get_team_points")
def get_team_points(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    result = {team.name: team.points for team in teams}
    return {"team_points": result}

@app.get("/get_available_drivers")
def get_available_drivers(db: Session = Depends(get_db)):
    drafted = []
    teams = db.query(models.Team).all()
    for team in teams:
        drafted.extend(json.loads(team.roster))
    undrafted = [driver for driver in fetched_drivers if driver not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    roster = json.loads(team.roster)
    if len(roster) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers!")
    # Check if driver already drafted across teams.
    teams = db.query(models.Team).all()
    for t in teams:
        if driver_name in json.loads(t.roster):
            raise HTTPException(status_code=400, detail="Driver already drafted.")
    roster.append(driver_name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    roster = json.loads(team.roster)
    if driver_name not in roster:
        raise HTTPException(status_code=400, detail="Driver not on this team.")
    roster.remove(driver_name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams(db: Session = Depends(get_db)):
    db.query(models.Team).delete()
    db.commit()
    return {"message": "All teams reset and drivers returned to pool!"}

# ---------- Locked Season Endpoints (For persisting season data) ----------

@app.post("/lock_teams")
def lock_teams(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    if len(teams) != 3:
        raise HTTPException(status_code=400, detail="We need exactly 3 teams to lock.")
    for team in teams:
        roster = json.loads(team.roster)
        if len(roster) != 6:
            raise HTTPException(status_code=400, detail=f"Team {team.name} does not have 6 drivers yet.")
    season_id = str(uuid.uuid4())
    teams_dict = {team.name: json.loads(team.roster) for team in teams}
    points_dict = {team.name: team.points for team in teams}
    # IMPORTANT: Persist locked season data to the database; do not use an in-memory dict.
    new_locked = models.LockedSeason(
        season_id = season_id,
        teams = json.dumps(teams_dict),
        points = json.dumps(points_dict),
        trade_history = json.dumps([]),
        race_points = json.dumps({}),      # for storing race-by-race breakdown
        processed_races = json.dumps([])     # to track which races have been processed
    )
    db.add(new_locked)
    db.commit()
    return {"message": "Teams locked for 2025 season!", "season_id": season_id}

@app.get("/get_season")
def get_season(season_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    return {
        "teams": json.loads(locked.teams),
        "points": json.loads(locked.points),
        "trade_history": json.loads(locked.trade_history),
        "race_points": json.loads(locked.race_points)
    }

@app.get("/get_undrafted_drivers")
def get_undrafted_drivers(season_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason)\
               .filter(models.LockedSeason.season_id == season_id)\
               .first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    # all possible drivers from startup fetch
    all_drivers = set(fetched_drivers)
    # drafted = union of every team’s roster in this locked season
    rosters = json.loads(locked.teams)
    drafted = {d for roster in rosters.values() for d in roster}
    undrafted = sorted(all_drivers - drafted)
    return {"undrafted": undrafted}

# ---------- Trade and Points Update Endpoints ----------

class LockedTradeRequest(BaseModel):
    from_team: str
    to_team: str
    drivers_from_team: List[str]
    drivers_to_team: List[str]
    from_team_points: int = 0
    to_team_points: int = 0

@app.post("/trade_locked")
def trade_locked(season_id: str, request: LockedTradeRequest, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    teams = json.loads(locked.teams)
    points = json.loads(locked.points)
    trade_history = json.loads(locked.trade_history)
    if request.from_team not in teams or request.to_team not in teams:
        raise HTTPException(status_code=404, detail="One or both teams not found in this season.")
    from_roster = teams[request.from_team]
    to_roster = teams[request.to_team]
    for drv in request.drivers_from_team:
        if drv not in from_roster:
            raise HTTPException(status_code=400, detail=f"{request.from_team} does not own {drv}")
    for drv in request.drivers_to_team:
        if drv not in to_roster:
            raise HTTPException(status_code=400, detail=f"{request.to_team} does not own {drv}")
    if len(request.drivers_from_team) != len(request.drivers_to_team):
        raise HTTPException(status_code=400, detail="Trade must have same number of drivers each way.")
    if request.from_team_points < 0 or request.to_team_points < 0:
        raise HTTPException(status_code=400, detail="Sweetener points cannot be negative.")
    if request.from_team_points > points.get(request.from_team, 0):
        raise HTTPException(status_code=400, detail=f"{request.from_team} does not have enough points.")
    if request.to_team_points > points.get(request.to_team, 0):
        raise HTTPException(status_code=400, detail=f"{request.to_team} does not have enough points.")
    # Process driver swap.
    for drv in request.drivers_from_team:
        from_roster.remove(drv)
    for drv in request.drivers_to_team:
        to_roster.remove(drv)
    from_roster.extend(request.drivers_to_team)
    to_roster.extend(request.drivers_from_team)
    # Transfer sweetener points.
    points[request.from_team] -= request.from_team_points
    points[request.to_team] += request.from_team_points
    points[request.to_team] -= request.to_team_points
    points[request.from_team] += request.to_team_points
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_log = f"On {time_str}, {request.from_team} traded {request.drivers_from_team} + {request.from_team_points} points to {request.to_team} for {request.drivers_to_team} + {request.to_team_points} points."
    trade_history.append(trade_log)
    locked.teams = json.dumps(teams)
    locked.points = json.dumps(points)
    locked.trade_history = json.dumps(trade_history)
    db.commit()
    return {
        "message": "Locked season trade completed!",
        "season_id": season_id,
        "from_team": {"name": request.from_team, "roster": from_roster, "points": points[request.from_team]},
        "to_team": {"name": request.to_team, "roster": to_roster, "points": points[request.to_team]},
        "trade_history": trade_history
    }

@app.post("/update_race_points")
def update_race_points(season_id: str, race_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    
    try:
        processed_races = json.loads(locked.processed_races)
    except Exception:
        processed_races = []

    # Our mapping of race names to their round numbers according to the Jolpi API.
    race_map = {
        "Bahrain": "4",
        "Saudi Arabia": "5",
        "Miami": "6",
        "Imola": "7",
        "Monaco": "8",
        "Spain": "9",
        "Canada": "10",
        "Austria": "11",
        "UK": "12",
        "Belgium": "13",
        "Hungary": "14",
        "Netherlands": "15",
        "Monza": "16",
        "Azerbaijan": "17",
        "Singapore": "18",
        "Texas": "19",
        "Mexico": "20",
        "Brazil": "21",
        "Vegas": "22",
        "Qatar": "23",
        "Abu Dhabi": "24"
    }
    # Our list of races in the season (display names)
    RACE_LIST = [
        "Bahrain", "Saudi Arabia", "Miami", "Imola", "Monaco", "Spain",
        "Canada", "Austria", "UK", "Belgium", "Hungary", "Netherlands",
        "Monza", "Azerbaijan", "Singapore", "Texas", "Mexico", "Brazil",
        "Vegas", "Qatar", "Abu Dhabi"
    ]

    # If the frontend sends "latest", determine the next unprocessed race.
    if race_id.lower() == "latest":
        next_race = None
        for race in RACE_LIST:
            if race not in processed_races:
                next_race = race
                break
        if not next_race:
            raise HTTPException(status_code=400, detail="No upcoming race data available.")
        # Now, use the mapping to get the proper round number.
        race_round = race_map.get(next_race)
        if not race_round:
            raise HTTPException(status_code=400, detail="Race mapping not found.")
        # We'll store data under the race's name (e.g. "Bahrain")
        current_race_name = next_race
        race_id = race_round  # Use the numeric round for the API call.
    else:
        # If a specific race_id is provided, look up its name.
        current_race_name = None
        for name, r in race_map.items():
            if r == race_id:
                current_race_name = name
                break
        if not current_race_name:
            raise HTTPException(status_code=400, detail="Invalid race id provided.")

    # Now fetch the race data from the Jolpi API
    try:
        response = requests.get(
            f"https://api.jolpi.ca/ergast/f1/2025/{race_id}/results.json",
            timeout=10
        )
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Error fetching race data.")
        race_data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching race data: {e}")

    try:
        race_results = race_data["MRData"]["RaceTable"]["Races"][0]["Results"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing race results: {e}")

    # Build driver points mapping from API data.
    driver_points = {}
    for result in race_results:
        driver_name = f"{result['Driver']['givenName']} {result['Driver']['familyName']}"
       # ✅ new code
position = int(result["position"])
if position <= 10:
    # use the real F1 points for P1–P10
    points_earned = float(result["points"])
elif 11 <= position <= 20:
    # custom fantasy points for 11th–20th
    custom_scale = {
        11: 0.5,
        12: 0.4,
        13: 0.3,
        14: 0.2,
        15: 0.1,
        16: 0.05,
        17: 0.04,
        18: 0.03,
        19: 0.02,
        20: 0.01,
    }
    points_earned = custom_scale.get(position, 0)
else:
    points_earned = 0

driver_points[driver_name] = points_earned

    # Update locked season data.
    teams = json.loads(locked.teams)  # teams: {TeamName: [driver1, driver2, ...]}
    points = json.loads(locked.points)
    try:
        race_points_data = json.loads(locked.race_points)
    except Exception:
        race_points_data = {}

    # For each team and each driver in that team,
    # update race_points for current race using the API data.
    for team, roster in teams.items():
        for driver in roster:
            pts = driver_points.get(driver, 0)
            if current_race_name not in race_points_data:
                race_points_data[current_race_name] = {}
            race_points_data[current_race_name][driver] = {"points": pts, "team": team}
            # Add these points to the overall team points.
            points[team] += pts

    processed_races.append(current_race_name)
    locked.points = json.dumps(points)
    locked.race_points = json.dumps(race_points_data)
    locked.processed_races = json.dumps(processed_races)
    db.commit()
    return {"message": "Race points updated successfully.", "points": points}