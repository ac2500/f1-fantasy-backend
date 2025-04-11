from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid
from typing import List
from datetime import datetime
import json
import logging

# Import database and models
from database import SessionLocal, engine, Base
import models

# Create database tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get a DB session for each request.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- In-memory Data for Draft Phase (Not persistent after lock) ----------
# The following in-memory data is no longer used for the locked season,
# but is still used while the draft is in progress.
registered_teams = {}   # e.g. {"TeamA": ["Driver1", ...], "TeamB": [...], ...}
team_points = {}        # e.g. {"TeamA": 0, "TeamB": 0, ...}
fetched_drivers = []    # from Jolpica

# ---------- After locking: store locked season in Neon ----------
# The locked season data will be stored permanently in the LockedSeason model.

# =========== 1) Fetch 2025 drivers on startup ===========
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"

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
    return {"message": "F1 Fantasy Backend with persistent data on Neon."}

# =========== 2) Draft Phase Endpoints ===========
@app.get("/register_team")
def register_team(team_name: str, db: SessionLocal = Depends(get_db)):
    # Check if team already exists (persistent now via the database)
    existing_team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if existing_team:
        return {"error": "Team name already exists."}
    # Create a new Team record with an empty roster (stored as JSON string) and 0 points.
    new_team = models.Team(name=team_name, roster=json.dumps([]), points=0)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams(db: SessionLocal = Depends(get_db)):
    teams = db.query(models.Team).all()
    result = {team.name: json.loads(team.roster) for team in teams}
    return {"teams": result}

@app.get("/get_team_points")
def get_team_points(db: SessionLocal = Depends(get_db)):
    teams = db.query(models.Team).all()
    result = {team.name: team.points for team in teams}
    return {"team_points": result}

@app.get("/get_available_drivers")
def get_available_drivers(db: SessionLocal = Depends(get_db)):
    # Available drivers are those not yet drafted.
    available = db.query(models.Driver).filter(models.Driver.drafted_by.is_(None)).all()
    available_names = [drv.name for drv in available]
    return {"drivers": available_names}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str, db: SessionLocal = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    roster = json.loads(team.roster)
    if len(roster) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers!")
    
    driver = db.query(models.Driver).filter(models.Driver.name == driver_name).first()
    if not driver:
        raise HTTPException(status_code=400, detail="Invalid driver name.")
    if driver.drafted_by is not None:
        raise HTTPException(status_code=400, detail="Driver already drafted.")
    
    # Update driver record and team roster.
    driver.drafted_by = team.name
    roster.append(driver.name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str, db: SessionLocal = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    
    roster = json.loads(team.roster)
    if driver_name not in roster:
        raise HTTPException(status_code=400, detail="Driver not on this team.")
    
    driver = db.query(models.Driver).filter(models.Driver.name == driver_name).first()
    if driver:
        driver.drafted_by = None
    roster.remove(driver_name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams(db: SessionLocal = Depends(get_db)):
    # Delete all teams and reset all drivers.
    db.query(models.Team).delete()
    drivers = db.query(models.Driver).all()
    for drv in drivers:
        drv.drafted_by = None
    db.commit()
    return {"message": "All teams reset and drivers returned to pool!"}

# =========== 3) Lock Teams: Create a Locked Season ===========
@app.post("/lock_teams")
def lock_teams(db: SessionLocal = Depends(get_db)):
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
    # Create a new LockedSeason record; note that 'processed_races' is initialized to an empty list.
    new_locked = models.LockedSeason(
        season_id=season_id,
        teams=json.dumps(teams_dict),
        points=json.dumps(points_dict),
        trade_history=json.dumps([]),
        processed_races=json.dumps([])
    )
    db.add(new_locked)
    db.commit()
    return {"message": "Teams locked for 2025 season!", "season_id": season_id}

@app.get("/get_season")
def get_season(season_id: str, db: SessionLocal = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    return {
        "teams": json.loads(locked.teams),
        "points": json.loads(locked.points),
        "trade_history": json.loads(locked.trade_history)
    }

# =========== 4) Trade in Locked Season (2-Sided Sweetener) ===========
class LockedTradeRequest(BaseModel):
    from_team: str
    to_team: str
    drivers_from_team: List[str]
    drivers_to_team: List[str]
    from_team_points: int = 0
    to_team_points: int = 0

@app.post("/trade_locked")
def trade_locked(season_id: str, request: LockedTradeRequest, db: SessionLocal = Depends(get_db)):
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
    
    # Execute the driver swap.
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
    trade_log = (f"On {time_str}, {request.from_team} traded {request.drivers_from_team} + "
                 f"{request.from_team_points} points to {request.to_team} for {request.drivers_to_team} + "
                 f"{request.to_team_points} points.")
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

# =========== 5) NEW: Update Race Points Endpoint ===========
# This endpoint manually fetches race results (for a specified race_id) from Jolpica,
# calculates the points earned by drivers, and updates the locked season's team points.
@app.post("/update_race_points")
def update_race_points(season_id: str, race_id: str, db: Session = Depends(get_db)):
    """
    Manually update the locked season points for a particular race.
    It fetches race results for the given race_id from the Jolpica API and updates team points.
    """
    locked_season = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked_season:
        raise HTTPException(status_code=404, detail="Season not found.")

    try:
        processed_races = json.loads(locked_season.processed_races)
    except Exception:
        processed_races = []

    if race_id in processed_races:
        raise HTTPException(status_code=400, detail="This race has already been processed.")

    # Fetch race results from Jolpica.
    try:
        # Note: Adjust the URL as per the Jolpica API specifications.
        response = requests.get(f"https://api.jolpi.ca/ergast/f1/2025/{race_id}/results.json", timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Error fetching race data.")
        race_data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching race data: {e}")

    # Parse race results (adjust parsing logic based on the actual API response).
    try:
        race_results = race_data["MRData"]["RaceTable"]["Races"][0]["Results"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing race results: {e}")

    # Create a mapping of driver names to points earned in this race.
    driver_points = {}
    for result in race_results:
        driver_name = f"{result['Driver']['givenName']} {result['Driver']['familyName']}"
        try:
            points_earned = float(result["points"])
        except Exception:
            points_earned = 0
        driver_points[driver_name] = points_earned

    teams = json.loads(locked_season.teams)    # e.g., {"TeamA": ["Driver1", ...], ...}
    points = json.loads(locked_season.points)  # e.g., {"TeamA": 50, "TeamB": 20, ...}

    # For each team, add the points earned by the drivers currently on the team.
    for team, roster in teams.items():
        race_total = 0
        for driver in roster:
            race_total += driver_points.get(driver, 0)
        points[team] += race_total

    locked_season.points = json.dumps(points)

    # Record the race as processed.
    processed_races.append(race_id)
    locked_season.processed_races = json.dumps(processed_races)

    # Optionally, add a note to the trade history.
    trade_history = json.loads(locked_season.trade_history)
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_history.append(f"Race {race_id} processed on {time_str}.")
    locked_season.trade_history = json.dumps(trade_history)

    db.commit()
    return {"message": "Race points updated successfully.", "points": points}