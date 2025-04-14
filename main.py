import os
import requests
import uuid
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------
# SQLAlchemy Setup for Persistent Draft Data
# ---------------------------
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable is not set!")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    points = Column(Integer, default=0)
    drivers = relationship("Driver", back_populates="team", cascade="all, delete-orphan")

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    team_id = Column(Integer, ForeignKey("teams.id"))
    team = relationship("Team", back_populates="drivers")

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# ---------------------------
# FastAPI App
# ---------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  # or your domain(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# In-Memory Data for Locked Season
# ---------------------------
locked_seasons = {}
# e.g.: locked_seasons[season_id] = {
#   "teams": { "TeamA": ["Driver1", ...], ... },
#   "points": { "TeamA": 100, "TeamB": 60, ... },
#   "trade_history": [],
#   "race_points": { "Bahrain": { "DriverName": {"points": X, "team": Y}, ... } }
# }

# ---------------------------
# Jolpica 2025 Drivers (fetch on startup)
# ---------------------------
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"
fetched_drivers = []

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

# ---------------------------
# Endpoints: Draft Phase (Persistent)
# ---------------------------
@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend: Persistent draft with Neon, locked season in memory."}

@app.get("/register_team")
def register_team(team_name: str, db: Session = Depends(get_db)):
    """Register a new team via GET param: e.g. /register_team?team_name=Alpine"""
    existing = db.query(Team).filter(Team.name == team_name).first()
    if existing:
        return {"error": "Team name already exists."}
    new_team = Team(name=team_name)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams(db: Session = Depends(get_db)):
    """Return all teams and their drivers from the DB."""
    teams = db.query(Team).all()
    result = {}
    for t in teams:
        result[t.name] = [d.name for d in t.drivers]
    return {"teams": result}

@app.get("/get_available_drivers")
def get_available_drivers(db: Session = Depends(get_db)):
    """Return drivers from fetched_drivers not yet drafted in the DB."""
    drafted = {d.name for t in db.query(Team).all() for d in t.drivers}
    undrafted = [drv for drv in fetched_drivers if drv not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    """
    Draft a driver with query params:
      POST /draft_driver?team_name=Alpine&driver_name=Pierre Gasly
    """
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    if len(team.drivers) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers.")

    existing_driver = db.query(Driver).filter(Driver.name == driver_name).first()
    if existing_driver:
        raise HTTPException(status_code=400, detail="Driver already drafted.")

    new_driver = Driver(name=driver_name, team=team)
    db.add(new_driver)
    db.commit()
    db.refresh(new_driver)
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    """
    Undo a draft with query params:
      POST /undo_draft?team_name=Alpine&driver_name=Pierre Gasly
    """
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    driver = db.query(Driver).filter(Driver.team_id == team.id, Driver.name == driver_name).first()
    if not driver:
        raise HTTPException(status_code=400, detail="Driver not on this team.")

    db.delete(driver)
    db.commit()
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams(db: Session = Depends(get_db)):
    """Clear all teams and drivers in the DB."""
    db.query(Driver).delete()
    db.query(Team).delete()
    db.commit()
    return {"message": "All teams and drivers reset successfully."}

# ---------------------------
# Locking the Season (In-Memory)
# ---------------------------
@app.post("/lock_teams")
def lock_teams(db: Session = Depends(get_db)):
    """Lock exactly 3 teams with 6 drivers each, storing them in memory for the 'locked season'."""
    teams = db.query(Team).all()
    if len(teams) != 3:
        raise HTTPException(status_code=400, detail="We need exactly 3 teams to lock.")
    for t in teams:
        if len(t.drivers) != 6:
            raise HTTPException(status_code=400, detail=f"Team {t.name} does not have 6 drivers yet.")

    season_id = str(uuid.uuid4())
    locked_seasons[season_id] = {
        "teams": {t.name: [d.name for d in t.drivers] for t in teams},
        "points": {t.name: t.points for t in teams},
        "trade_history": [],
        "race_points": {}
    }
    return {"message": "Teams locked for 2025 season!", "season_id": season_id}

@app.get("/get_season")
def get_season(season_id: str):
    """Fetch the locked season data from in-memory dictionary."""
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    return locked_seasons[season_id]

# ---------------------------
# Trades in Locked Season (In-Memory)
# ---------------------------
class LockedTradeRequest(BaseModel):
    from_team: str
    to_team: str
    drivers_from_team: List[str]
    drivers_to_team: List[str]
    from_team_points: int = 0
    to_team_points: int = 0

@app.post("/trade_locked")
def trade_locked(season_id: str, request: LockedTradeRequest):
    """Perform a balanced trade in the locked season, with optional points sweetener from both sides."""
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")

    season_data = locked_seasons[season_id]
    teams_dict = season_data["teams"]
    points_dict = season_data["points"]

    if request.from_team not in teams_dict or request.to_team not in teams_dict:
        raise HTTPException(status_code=404, detail="One or both teams not found in this locked season.")

    from_roster = teams_dict[request.from_team]
    to_roster = teams_dict[request.to_team]

    # Validate driver ownership
    for drv in request.drivers_from_team:
        if drv not in from_roster:
            raise HTTPException(status_code=400, detail=f"{request.from_team} does not own {drv}")
    for drv in request.drivers_to_team:
        if drv not in to_roster:
            raise HTTPException(status_code=400, detail=f"{request.to_team} does not own {drv}")

    # Balanced trade: same number of drivers each way
    if len(request.drivers_from_team) != len(request.drivers_to_team):
        raise HTTPException(status_code=400, detail="Trade must have same number of drivers each way.")

    # Validate sweetener points
    if request.from_team_points < 0 or request.to_team_points < 0:
        raise HTTPException(status_code=400, detail="Sweetener points cannot be negative.")
    if request.from_team_points > points_dict.get(request.from_team, 0):
        raise HTTPException(status_code=400, detail=f"{request.from_team} lacks enough points.")
    if request.to_team_points > points_dict.get(request.to_team, 0):
        raise HTTPException(status_code=400, detail=f"{request.to_team} lacks enough points.")

    # Remove the specified drivers
    for drv in request.drivers_from_team:
        from_roster.remove(drv)
    for drv in request.drivers_to_team:
        to_roster.remove(drv)

    # Add them to the other side
    from_roster.extend(request.drivers_to_team)
    to_roster.extend(request.drivers_from_team)

    # Transfer sweetener points
    points_dict[request.from_team] -= request.from_team_points
    points_dict[request.to_team] += request.from_team_points
    points_dict[request.to_team] -= request.to_team_points
    points_dict[request.from_team] += request.to_team_points

    # Log the trade
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    desc = (f"On {time_str}, {request.from_team} traded {request.drivers_from_team} + "
            f"{request.from_team_points} points to {request.to_team} for "
            f"{request.drivers_to_team} + {request.to_team_points} points.")
    season_data["trade_history"].append(desc)

    return {
        "message": "Locked season trade completed!",
        "season_id": season_id,
        "from_team": {
            "name": request.from_team,
            "roster": from_roster,
            "points": points_dict[request.from_team]
        },
        "to_team": {
            "name": request.to_team,
            "roster": to_roster,
            "points": points_dict[request.to_team]
        },
        "trade_history": season_data["trade_history"]
    }

# ---------------------------
# Race Points Update (In-Memory)
# ---------------------------
@app.post("/update_race_points")
def update_race_points_endpoint(season_id: str, race_id: str = "Bahrain"):
    """
    Example: /update_race_points?season_id=xxx&race_id=Bahrain
    Hard-coded that 'Bahrain' = round 4, referencing https://api.jolpi.ca/ergast/f1/2025/4/results.json
    """
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    season_data = locked_seasons[season_id]

    # Hard-code: if race_id == 'Bahrain', we use round 4
    round_number = 4 if race_id == "Bahrain" else 4  # Adjust logic if you have multiple
    # (You could have a dictionary if you want other races: 'Saudi Arabia': 5, etc.)

    jolpica_url = f"https://api.jolpica.ca/ergast/f1/2025/{round_number}/results.json"

    try:
        resp = requests.get(jolpica_url, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Error fetching race data from Jolpica.")
        race_data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching race data: {e}")

    # Parse the race data (Ergast-like structure)
    try:
        races = race_data["MRData"]["RaceTable"]["Races"]
        if not races:
            raise HTTPException(status_code=400, detail="No race data found.")
        race_info = races[0]
        results = race_info["Results"]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing race data: {e}")

    if "race_points" not in season_data:
        season_data["race_points"] = {}
    season_data["race_points"][race_id] = {}

    def find_driver_team(driver_name):
        for tm, drvs in season_data["teams"].items():
            if driver_name in drvs:
                return tm
        return None

    for result in results:
        drv = result["Driver"]
        driver_name = f"{drv['givenName']} {drv['familyName']}"
        pts_str = result.get("points", "0")
        try:
            pts = int(pts_str)
        except:
            pts = 0
        season_data["race_points"][race_id][driver_name] = {
            "points": pts,
            "team": find_driver_team(driver_name)
        }
        the_team = find_driver_team(driver_name)
        if the_team:
            if the_team not in season_data["points"]:
                season_data["points"][the_team] = 0
            season_data["points"][the_team] += pts

    return {"message": f"Race points for {race_id} updated successfully!"}