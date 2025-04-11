from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid
from typing import List
from datetime import datetime
import json

# DATABASE SETUP (assumes these files are created)
from database import SessionLocal, engine, Base
import models

# Create the database tables if they do not exist yet.
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

# ---------- Fallback driver list and Driver fetching ----------
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

JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"

# =========== 1) Startup: Fetch drivers and sync with the DB ===========
@app.on_event("startup")
def fetch_2025_drivers_on_startup():
    try:
        resp = requests.get(JOLPICA_2025_URL, timeout=10)
        if resp.status_code != 200:
            print("⚠️ Could not fetch 2025 drivers from Jolpica. Using fallback.")
            driver_names = fallback_2025_driver_list()
        else:
            data = resp.json()
            jolpica_drivers = data["MRData"]["DriverTable"]["Drivers"]
            driver_names = [
                f"{drv['givenName']} {drv['familyName']}" for drv in jolpica_drivers
            ]
            print(f"✅ Fetched {len(driver_names)} drivers from Jolpica.")
    except Exception as e:
        print(f"⚠️ Exception fetching drivers: {e}")
        driver_names = fallback_2025_driver_list()

    db = SessionLocal()
    try:
        # Sync: insert each driver if not already present.
        existing = db.query(models.Driver).all()
        existing_names = {drv.name for drv in existing}
        for name in driver_names:
            if name not in existing_names:
                new_driver = models.Driver(name=name, drafted_by=None)
                db.add(new_driver)
        db.commit()
    except Exception as e:
        print(f"Error syncing drivers to DB: {e}")
        db.rollback()
    finally:
        db.close()

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend with persistent data on Neon."}

# =========== 2) Draft Phase Endpoints using the Database ===========

# Replace in-memory team registration with a persistent Team record.
@app.get("/register_team")
def register_team(team_name: str, db: SessionLocal = Depends(get_db)):
    # Check if team already exists
    existing_team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if existing_team:
        return {"error": "Team name already exists."}
    # Create a new Team record.
    new_team = models.Team(name=team_name, roster=json.dumps([]), points=0)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return {"message": f"{team_name} registered successfully!"}

# Get all registered teams from the database.
@app.get("/get_registered_teams")
def get_registered_teams(db: SessionLocal = Depends(get_db)):
    teams = db.query(models.Team).all()
    result = {team.name: json.loads(team.roster) for team in teams}
    return {"teams": result}

# Get the points for each team from the database.
@app.get("/get_team_points")
def get_team_points(db: SessionLocal = Depends(get_db)):
    teams = db.query(models.Team).all()
    result = {team.name: team.points for team in teams}
    return {"team_points": result}

# Get available drivers (those that are not yet drafted).
@app.get("/get_available_drivers")
def get_available_drivers(db: SessionLocal = Depends(get_db)):
    available = db.query(models.Driver).filter(models.Driver.drafted_by.is_(None)).all()
    available_names = [drv.name for drv in available]
    return {"drivers": available_names}

# Draft a driver to a team.
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

# Undo a draft: remove a driver from a team.
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

# Reset teams: delete all teams and reset drafted drivers.
@app.post("/reset_teams")
def reset_teams(db: SessionLocal = Depends(get_db)):
    # Delete all teams.
    db.query(models.Team).delete()
    # Reset all drivers.
    drivers = db.query(models.Driver).all()
    for drv in drivers:
        drv.drafted_by = None
    db.commit()
    return {"message": "All teams reset and drivers returned to pool!"}

# =========== 3) Lock Teams: create a locked season (persistent) ===========
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
    # Create a new LockedSeason record (assumes such a model exists)
    new_locked = models.LockedSeason(
        season_id=season_id,
        teams=json.dumps(teams_dict),
        points=json.dumps(points_dict),
        trade_history=json.dumps([])
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

# =========== 4) Trade in Locked Season (2-sided sweetener with trade history) ===========
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