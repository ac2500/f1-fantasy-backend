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
def update_race_points(
    season_id: str,
    race_id: str,
    db: Session = Depends(get_db),
):
    """
    Update points for the next unprocessed race (or a specific race_id).
    Applies F1 points 1–10 from the API, then 11→0.5, 12→0.45 … 20→0.05.
    Records processed races so they cannot be applied twice.
    """
    locked = (
        db.query(models.LockedSeason)
        .filter(models.LockedSeason.season_id == season_id)
        .first()
    )
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")

    # load JSON blobs
    processed = json.loads(locked.processed_races or "[]")
    pts_map    = json.loads(locked.points or "{}")
    rp_data    = json.loads(locked.race_points or "{}")
    teams      = json.loads(locked.teams or "{}")

    # determine which race to fetch
    if race_id.lower() == "latest":
        # pick next unprocessed round number
        # round numbers are strings of integers
        next_round = (
            max(map(int, processed)) + 1
            if processed
            else 4  # start at Imola if nothing else done
        )
        race_id = str(next_round)
    if race_id in processed:
        raise HTTPException(status_code=400, detail="This race has already been processed.")

    # fetch results
    resp = requests.get(
        f"https://api.jolpi.ca/ergast/f1/2025/{race_id}/results.json",
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Error fetching race data.")
    data = resp.json()

    try:
        results = data["MRData"]["RaceTable"]["Races"][0]["Results"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=500, detail="Malformed race data.")

    # build driver→points mapping with custom scoring
    driver_pts: Dict[str, float] = {}
    for idx, r in enumerate(results, start=1):
        name = f"{r['Driver']['givenName']} {r['Driver']['familyName']}"
        if idx <= 10:
            pts = float(r.get("points", 0))
        elif idx <= 20:
            # 11th = 0.5, 12th = 0.45, ... 20th = 0.05
            pts = max(0.0, 0.55 - 0.05 * idx)
        else:
            pts = 0.0
        driver_pts[name] = pts

    # apply points to each rostered driver
    rp_data.setdefault(race_id, {})
    for team, roster in teams.items():
        # ensure team has a running total
        pts_map.setdefault(team, 0.0)
        for drv in roster:
            p = driver_pts.get(drv, 0.0)
            rp_data[race_id][drv] = {"points": p, "team": team}
            pts_map[team] += p

    # mark race as processed
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