import os
import requests
import uuid
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# SQLAlchemy imports
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

# ------------------------------------------------------------------------------
# DATABASE SETUP (Persistent for Draft Phase)
# ------------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable is not set!")

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ------------------------------------------------------------------------------
# SQLAlchemy Models for Teams and Drivers (Draft Data)
# ------------------------------------------------------------------------------
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

# Create tables if they don't exist.
Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# FastAPI App Setup
# ------------------------------------------------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],  # adjust as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency: get DB session for endpoints.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------------------------------------------------------------------
# In-Memory Data for Locked Season (Not persistent yet)
# ------------------------------------------------------------------------------
locked_seasons = {}
# locked_seasons[season_id] format:
# {
#   "teams": { <team_name>: [<driver names>], ... },
#   "points": { <team_name>: <points>, ... },
#   "trade_history": [ "On DATE, ..." ],
#   "race_points": { <race_id>: { <driver_name>: {"points": <points>, "team": <team_name>}, ... }, ... }
# }

# ------------------------------------------------------------------------------
# Pydantic Schemas for Input Validation
# ------------------------------------------------------------------------------
class TeamCreate(BaseModel):
    team_name: str

class DraftDriver(BaseModel):
    team_name: str
    driver_name: str

class LockedTradeRequest(BaseModel):
    from_team: str
    to_team: str
    drivers_from_team: List[str]
    drivers_to_team: List[str]
    from_team_points: int = 0  # points from from_team to to_team
    to_team_points: int = 0    # points from to_team to from_team

# ------------------------------------------------------------------------------
# In-Memory Data for Draft Phase Fallback (Jolpica drivers)
# ------------------------------------------------------------------------------
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"
fetched_drivers = []  # list of driver names

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
        fetched_drivers = [f"{drv['givenName']} {drv['familyName']}" for drv in jolpica_drivers]
        print(f"✅ Fetched {len(fetched_drivers)} drivers from Jolpica.")
    except Exception as e:
        print(f"⚠️ Exception fetching Jolpica 2025 drivers: {e}")
        fetched_drivers = fallback_2025_driver_list()

# ------------------------------------------------------------------------------
# Endpoints: Draft Phase (Persistent, using DB)
# ------------------------------------------------------------------------------

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend Persistent with Neon DB integration."}

@app.post("/register_team")
def register_team_endpoint(team: TeamCreate, db: Session = Depends(get_db)):
    # Check if team already exists in DB.
    existing = db.query(Team).filter(Team.name == team.team_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team name already exists.")
    new_team = Team(name=team.team_name)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return {"message": f"{team.team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    result = {}
    for team in teams:
        result[team.name] = [driver.name for driver in team.drivers]
    return {"teams": result}

@app.get("/get_team_points")
def get_team_points(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    result = {}
    for team in teams:
        result[team.name] = team.points
    return {"team_points": result}

@app.get("/get_available_drivers")
def get_available_drivers(db: Session = Depends(get_db)):
    # Determine which drivers are already drafted.
    drafted_drivers = {driver.name for team in db.query(Team).all() for driver in team.drivers}
    available = [driver for driver in fetched_drivers if driver not in drafted_drivers]
    return {"drivers": available}

@app.post("/draft_driver")
def draft_driver_endpoint(draft: DraftDriver, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.name == draft.team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    if len(team.drivers) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers.")
    # Check if driver is already drafted
    existing_driver = db.query(Driver).filter(Driver.name == draft.driver_name).first()
    if existing_driver:
        raise HTTPException(status_code=400, detail="Driver already drafted.")
    new_driver = Driver(name=draft.driver_name, team=team)
    db.add(new_driver)
    db.commit()
    db.refresh(new_driver)
    return {"message": f"{draft.driver_name} drafted by {draft.team_name}!"}

@app.post("/undo_draft")
def undo_draft_endpoint(team_name: str, driver_name: str, db: Session = Depends(get_db)):
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
def reset_teams_endpoint(db: Session = Depends(get_db)):
    db.query(Driver).delete()
    db.query(Team).delete()
    db.commit()
    return {"message": "All teams and drivers reset."}

# ------------------------------------------------------------------------------
# Endpoints: Locked Season & Trades (In-Memory)
# ------------------------------------------------------------------------------
@app.post("/lock_teams")
def lock_teams_endpoint(db: Session = Depends(get_db)):
    # Retrieve all teams from DB and ensure exactly 3 teams exist with 6 drivers each.
    teams = db.query(Team).all()
    if len(teams) != 3:
        raise HTTPException(status_code=400, detail="We need exactly 3 teams to lock.")
    for team in teams:
        if len(team.drivers) != 6:
            raise HTTPException(status_code=400, detail=f"Team {team.name} does not have 6 drivers yet.")
    season_id = str(uuid.uuid4())
    # Build locked season structure from DB data
    locked_seasons[season_id] = {
        "teams": {team.name: [driver.name for driver in team.drivers] for team in teams},
        "points": {team.name: team.points for team in teams},
        "trade_history": [],
        "race_points": {}  # to be filled by update_race_points endpoint
    }
    return {"message": "Teams locked for 2025 season!", "season_id": season_id}

@app.get("/get_season")
def get_season_endpoint(season_id: str):
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    return locked_seasons[season_id]

@app.post("/trade_locked")
def trade_locked_endpoint(season_id: str, request: LockedTradeRequest):
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    season_data = locked_seasons[season_id]
    teams_locked = season_data["teams"]
    points_locked = season_data["points"]

    if request.from_team not in teams_locked or request.to_team not in teams_locked:
        raise HTTPException(status_code=404, detail="One or both teams not found in this season.")

    from_roster = teams_locked[request.from_team]
    to_roster = teams_locked[request.to_team]

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
    if request.from_team_points > points_locked.get(request.from_team, 0):
        raise HTTPException(status_code=400, detail=f"{request.from_team} lacks sufficient points.")
    if request.to_team_points > points_locked.get(request.to_team, 0):
        raise HTTPException(status_code=400, detail=f"{request.to_team} lacks sufficient points.")

    for drv in request.drivers_from_team:
        from_roster.remove(drv)
    for drv in request.drivers_to_team:
        to_roster.remove(drv)

    from_roster.extend(request.drivers_to_team)
    to_roster.extend(request.drivers_from_team)

    points_locked[request.from_team] -= request.from_team_points
    points_locked[request.to_team] += request.from_team_points

    points_locked[request.to_team] -= request.to_team_points
    points_locked[request.from_team] += request.to_team_points

    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_description = (f"On {time_str}, {request.from_team} traded {request.drivers_from_team} + "
                         f"{request.from_team_points} points to {request.to_team} for "
                         f"{request.drivers_to_team} + {request.to_team_points} points.")
    season_data["trade_history"].append(trade_description)

    return {
        "message": "Locked season trade completed!",
        "season_id": season_id,
        "from_team": {"name": request.from_team, "roster": from_roster, "points": points_locked[request.from_team]},
        "to_team": {"name": request.to_team, "roster": to_roster, "points": points_locked[request.to_team]},
        "trade_history": season_data["trade_history"]
    }

@app.post("/update_race_points")
def update_race_points(season_id: str, race_id: str = "latest"):
    # Verify the locked season exists.
    if season_id not in locked_seasons:
        raise HTTPException(status_code=404, detail="Season not found.")
    
    season_data = locked_seasons[season_id]
    
    # Hypothetical call to the Jolpica API for race points.
    # Replace the URL and parsing with the actual Jolpica F1 API details.
    try:
        # Example URL (you must adjust this to the correct endpoint of the Jolpica API)
        jolpica_race_url = f"https://api.jolpica.com/f1/races/{race_id}/points"
        response = requests.get(jolpica_race_url, timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Error fetching race data from Jolpica.")
        race_data = response.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching race data: {e}")
    
    # Assume race_data is in the format: {"driverPoints": {"Lewis Hamilton": 25, "Max Verstappen": 18, ...}}
    driver_points_dict = race_data.get("driverPoints", {})
    
    if "race_points" not in season_data:
        season_data["race_points"] = {}
    season_data["race_points"][race_id] = {}
    
    # Helper function: find driver team from locked teams.
    def find_driver_team(driver_name):
        for team, drivers in season_data["teams"].items():
            if driver_name in drivers:
                return team
        return None

    # Update race_points and also update team totals.
    for driver_name, pts in driver_points_dict.items():
        season_data["race_points"][race_id][driver_name] = {
            "points": pts,
            "team": find_driver_team(driver_name)
        }
        team = find_driver_team(driver_name)
        if team:
            # Update team totals.
            if team not in season_data["points"]:
                season_data["points"][team] = 0
            season_data["points"][team] += pts

    return {"message": f"Race points for {race_id} updated successfully!"}