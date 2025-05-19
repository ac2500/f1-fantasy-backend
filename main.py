# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid
import json
from typing import List
from datetime import datetime

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models

# Create database tables if they do not exist.
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

# ------------------------------------------------------------------------------
# Draft-phase driver cache
# ------------------------------------------------------------------------------
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"
fetched_drivers: List[str] = []

@app.on_event("startup")
def fetch_2025_drivers_on_startup():
    global fetched_drivers
    try:
        resp = requests.get(JOLPICA_2025_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        jolpica_drivers = data["MRData"]["DriverTable"]["Drivers"]
        fetched_drivers = [
            f"{drv['givenName']} {drv['familyName']}"
            for drv in jolpica_drivers
        ]
        print(f"✅ Fetched {len(fetched_drivers)} drivers from Jolpica.")
    except Exception as e:
        print(f"⚠️ Could not fetch drivers from Jolpica ({e}); using fallback.")
        fetched_drivers = fallback_2025_driver_list()

def fallback_2025_driver_list() -> List[str]:
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

# ------------------------------------------------------------------------------
# Public endpoints
# ------------------------------------------------------------------------------

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend with persistent data on Neon."}

@app.get("/register_team")
def register_team(team_name: str, db: Session = Depends(get_db)):
    if db.query(models.Team).filter(models.Team.name == team_name).first():
        return {"error": "Team name already exists."}
    team = models.Team(name=team_name, roster=json.dumps([]), points=0)
    db.add(team)
    db.commit()
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    return {"teams": {t.name: json.loads(t.roster) for t in teams}}

@app.get("/get_team_points")
def get_team_points(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    return {"team_points": {t.name: t.points for t in teams}}

@app.get("/get_available_drivers")
def get_available_drivers(db: Session = Depends(get_db)):
    global fetched_drivers
    # collect all drafted names
    drafted = []
    for t in db.query(models.Team).all():
        drafted.extend(json.loads(t.roster))
    # filter our cache
    undrafted = [d for d in fetched_drivers if d not in drafted]
    return {"drivers": undrafted}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if not team:
        raise HTTPException(404, "Team not found.")
    roster = json.loads(team.roster)
    if len(roster) >= 6:
        raise HTTPException(400, "Team already has 6 drivers!")
    # check global uniqueness
    for t in db.query(models.Team).all():
        if driver_name in json.loads(t.roster):
            raise HTTPException(400, "Driver already drafted.")
    roster.append(driver_name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name == team_name).first()
    if not team:
        raise HTTPException(404, "Team not found.")
    roster = json.loads(team.roster)
    if driver_name not in roster:
        raise HTTPException(400, "Driver not on this team.")
    roster.remove(driver_name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} removed from {team_name}."}

@app.post("/reset_teams")
def reset_teams(db: Session = Depends(get_db)):
    db.query(models.Team).delete()
    db.commit()
    return {"message": "All teams reset and drivers returned to pool!"}

# ------------------------------------------------------------------------------
# Locked season endpoints
# ------------------------------------------------------------------------------

@app.post("/lock_teams")
def lock_teams(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    if len(teams) != 3:
        raise HTTPException(400, "We need exactly 3 teams to lock.")
    for t in teams:
        if len(json.loads(t.roster)) != 6:
            raise HTTPException(400, f"Team {t.name} does not have 6 drivers.")
    season_id = str(uuid.uuid4())
    teams_dict = {t.name: json.loads(t.roster) for t in teams}
    points_dict = {t.name: t.points for t in teams}
    locked = models.LockedSeason(
        season_id=season_id,
        teams=json.dumps(teams_dict),
        points=json.dumps(points_dict),
        trade_history=json.dumps([]),
        race_points=json.dumps({}),
        processed_races=json.dumps([])
    )
    db.add(locked)
    db.commit()
    return {"message": "Teams locked for 2025 season!", "season_id": season_id}

@app.get("/get_season")
def get_season(season_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked:
        raise HTTPException(404, "Season not found.")
    return {
        "teams": json.loads(locked.teams),
        "points": json.loads(locked.points),
        "trade_history": json.loads(locked.trade_history),
        "race_points": json.loads(locked.race_points),
        "processed_races": json.loads(locked.processed_races)
    }

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
        raise HTTPException(404, "Season not found.")
    teams = json.loads(locked.teams)
    points = json.loads(locked.points)
    history = json.loads(locked.trade_history)

    # validation omitted for brevity… (keep your existing checks)

    # swap drivers
    for d in request.drivers_from_team:
        teams[request.from_team].remove(d)
    for d in request.drivers_to_team:
        teams[request.to_team].remove(d)
    teams[request.from_team].extend(request.drivers_to_team)
    teams[request.to_team].extend(request.drivers_from_team)

    # sweeteners
    points[request.from_team] -= request.from_team_points
    points[request.to_team]   += request.from_team_points
    points[request.to_team]   -= request.to_team_points
    points[request.from_team] += request.to_team_points

    # log it
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append(f"On {time_str}, {request.from_team} traded {request.drivers_from_team} + "
                   f"{request.from_team_points}pts to {request.to_team} for "
                   f"{request.drivers_to_team} + {request.to_team_points}pts.")

    # persist
    locked.teams         = json.dumps(teams)
    locked.points        = json.dumps(points)
    locked.trade_history = json.dumps(history)
    db.commit()

    return {"message": "Locked season trade completed!", "trade_history": history}

@app.post("/update_race_points")
def update_race_points(season_id: str, race_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason) \
               .filter(models.LockedSeason.season_id == season_id) \
               .first()
    if not locked:
        raise HTTPException(404, "Season not found.")

    processed = json.loads(locked.processed_races or "[]")
    if race_id in processed:
        raise HTTPException(400, "This race has already been processed.")

    # fetch results from Jolpica API
    resp = requests.get(
        f"https://api.jolpi.ca/ergast/f1/2025/{race_id}/results.json",
        timeout=10
    )
    if resp.status_code != 200:
        raise HTTPException(400, "Error fetching race data.")
    data = resp.json()
    try:
        results = data["MRData"]["RaceTable"]["Races"][0]["Results"]
    except Exception:
        raise HTTPException(500, "Malformed race data.")

    # 4) Build driver→points map (API gives 1–10; custom for 11–20)
    custom = {
        11: 0.5, 12: 0.4, 13: 0.3, 14: 0.2, 15: 0.1,
        16: 0.05,17: 0.04,18: 0.03,19: 0.02,20: 0.01
    }
    driver_pts: Dict[str, float] = {}
    for idx, r in enumerate(results, start=1):
        name = f"{r['Driver']['givenName']} {r['Driver']['familyName']}"
        if idx <= 10:
            # trust the API’s points field for P1–P10
            pts = float(r.get("points", 0))
        elif idx <= 20:
            # use our custom half-point scheme for P11–P20
            pts = custom.get(idx, 0.0)
        else:
            pts = 0.0
        driver_pts[name] = pts

    # load existing locked-season data
    teams   = json.loads(locked.teams)
    pts_map = json.loads(locked.points)
    rp_data = json.loads(locked.race_points or "{}")

    # apply points for each rostered driver
    rp_data.setdefault(race_id, {})
    for team, roster in teams.items():
        for drv in roster:
            p = driver_pts.get(drv, 0)
            rp_data[race_id][drv] = {"points": p, "team": team}
            pts_map[team] += p

    # mark this race as processed
    processed.append(race_id)
    locked.points          = json.dumps(pts_map)
    locked.race_points     = json.dumps(rp_data)
    locked.processed_races = json.dumps(processed)

    db.commit()
    return {"message": "Race points updated successfully.", "points": pts_map}

@app.get("/get_free_agents")
def get_free_agents(season_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id == season_id).first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    # load the roster for this season
    teams = json.loads(locked.teams)
    # gather all drafted drivers
    drafted = {d for roster in teams.values() for d in roster}
    # get the original pool (from fetched_drivers or wherever you stored them)
    all_drivers = fetched_drivers  
    # filter out those already drafted in this locked season
    undrafted = [d for d in all_drivers if d not in drafted]
    return {"drivers": undrafted}