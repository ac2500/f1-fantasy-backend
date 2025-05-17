# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests, uuid, json
from typing import List
from datetime import datetime

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models

# ------------------------------------------------------------------------------
# Boilerplate & startup
# ------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ac2500.github.io"],
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

# Global driver list fetched at startup (for draft phase)
JOLPICA_2025_URL = "https://api.jolpi.ca/ergast/f1/2025/drivers.json"
fetched_drivers: List[str] = []

@app.on_event("startup")
def fetch_2025_drivers_on_startup():
    global fetched_drivers
    try:
        resp = requests.get(JOLPICA_2025_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        fetched_drivers = [
            f"{d['givenName']} {d['familyName']}"
            for d in data["MRData"]["DriverTable"]["Drivers"]
        ]
        print(f"✅ Fetched {len(fetched_drivers)} drivers from Jolpica.")
    except Exception:
        print("⚠️ Could not fetch drivers from Jolpica, using fallback.")
        fetched_drivers = [
            "Max Verstappen","Liam Lawson","Lando Norris","Oscar Piastri",
            "Charles Leclerc","Lewis Hamilton","George Russell",
            "Andrea Kimi Antonelli","Fernando Alonso","Lance Stroll",
            "Pierre Gasly","Jack Doohan","Esteban Ocon","Oliver Bearman",
            "Isack Hadjar","Yuki Tsunoda","Alexander Albon","Carlos Sainz Jr.",
            "Nico Hulkenberg","Gabriel Bortoleto"
        ]

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend with persistent data on Neon."}

# ------------------------------------------------------------------------------
# Draft‐phase endpoints
# ------------------------------------------------------------------------------

@app.get("/register_team")
def register_team(team_name: str, db: Session = Depends(get_db)):
    if db.query(models.Team).filter(models.Team.name==team_name).first():
        return {"error": "Team name already exists."}
    team = models.Team(name=team_name, roster=json.dumps([]), points=0)
    db.add(team); db.commit(); db.refresh(team)
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
    drafted = []
    for t in db.query(models.Team).all():
        drafted.extend(json.loads(t.roster))
    return {"drivers": [d for d in fetched_drivers if d not in drafted]}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name==team_name).first()
    if not team:
        raise HTTPException(404, "Team not found.")
    roster = json.loads(team.roster)
    if len(roster)>=6:
        raise HTTPException(400, "Team already has 6 drivers!")
    # ensure not already drafted
    for t in db.query(models.Team).all():
        if driver_name in json.loads(t.roster):
            raise HTTPException(400, "Driver already drafted.")
    roster.append(driver_name)
    team.roster = json.dumps(roster)
    db.commit()
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(models.Team).filter(models.Team.name==team_name).first()
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
# Locked‐season endpoints
# ------------------------------------------------------------------------------

@app.post("/lock_teams")
def lock_teams(db: Session = Depends(get_db)):
    teams = db.query(models.Team).all()
    if len(teams)!=3:
        raise HTTPException(400, "We need exactly 3 teams to lock.")
    for t in teams:
        if len(json.loads(t.roster))!=6:
            raise HTTPException(400, f"Team {t.name} does not have 6 drivers.")
    season_id = str(uuid.uuid4())
    new = models.LockedSeason(
        season_id       = season_id,
        teams           = json.dumps({t.name: json.loads(t.roster) for t in teams}),
        points          = json.dumps({t.name: t.points for t in teams}),
        trade_history   = json.dumps([]),
        race_points     = json.dumps({}),
        processed_races = json.dumps([])
    )
    db.add(new); db.commit()
    return {"message":"Teams locked for 2025 season!","season_id":season_id}

@app.get("/get_season")
def get_season(season_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id==season_id).first()
    if not locked:
        raise HTTPException(404, "Season not found.")
    return {
        "teams":         json.loads(locked.teams),
        "points":        json.loads(locked.points),
        "trade_history": json.loads(locked.trade_history),
        "race_points":   json.loads(locked.race_points)
    }
@app.get("/get_free_agents")
def get_free_agents(season_id: str, db: Session = Depends(get_db)):
    # look up the locked season
    locked = db.query(models.LockedSeason) \
               .filter(models.LockedSeason.season_id == season_id) \
               .first()
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")
    # pull out each team’s roster
    teams_dict = json.loads(locked.teams)      # { "TeamA": [...], "TeamB": [...], ... }
    # flatten into one list
    drafted = [d for roster in teams_dict.values() for d in roster]
    # use your fetched_drivers list to compute “free” drivers
    free_agents = [d for d in fetched_drivers if d not in drafted]
    return {"free_agents": free_agents}
# ------------------------------------------------------------------------------
# Trade + Free-Agency + Points update
# ------------------------------------------------------------------------------

class LockedTradeRequest(BaseModel):
    from_team:         str
    to_team:           str
    drivers_from_team: List[str]
    drivers_to_team:   List[str]
    from_team_points:  float = 0
    to_team_points:    float = 0

@app.post("/trade_locked")
def trade_locked(
    season_id: str,
    req: LockedTradeRequest,
    db: Session = Depends(get_db),
):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id==season_id).first()
    if not locked:
        raise HTTPException(404, "Season not found.")
    teams        = json.loads(locked.teams)
    points       = json.loads(locked.points)
    history      = json.loads(locked.trade_history)
    FT, TT       = req.from_team, req.to_team
    from_free    = (FT == "Free Agency")
    to_free      = (TT == "Free Agency")

    # Validate teams or free-agency
    if not from_free and FT not in teams:
        raise HTTPException(404, f"{FT} not in this season.")
    if not to_free   and TT not in teams:
        raise HTTPException(404, f"{TT} not in this season.")
    if from_free and to_free:
        raise HTTPException(400, "Invalid trade: both sides Free Agency.")

    # Validate drivers exist where they should
    if not from_free:
        for d in req.drivers_from_team:
            if d not in teams[FT]:
                raise HTTPException(400, f"{FT} does not own {d}.")
    if not to_free:
        for d in req.drivers_to_team:
            if d not in teams[TT]:
                raise HTTPException(400, f"{TT} does not own {d}.")

    # Allow equal‐length swaps only
    if len(req.drivers_from_team) != len(req.drivers_to_team):
        raise HTTPException(400, "Must exchange equal numbers of drivers.")

    # Sweetener points can’t be negative or exceed balance
    if req.from_team_points < 0 or req.to_team_points < 0:
        raise HTTPException(400, "Sweetener points cannot be negative.")
    if not from_free and req.from_team_points > points.get(FT,0):
        raise HTTPException(400, f"{FT} lacks {req.from_team_points} points.")
    if not to_free   and req.to_team_points   > points.get(TT,0):
        raise HTTPException(400, f"{TT} lacks {req.to_team_points} points.")

    # Process driver moves
    if not from_free:
        for d in req.drivers_from_team:
            teams[FT].remove(d)
    if not to_free:
        for d in req.drivers_to_team:
            teams[TT].remove(d)

    if not to_free:
        teams[TT].extend(req.drivers_from_team)
    if not from_free:
        teams[FT].extend(req.drivers_to_team)

    # Transfer sweetener
    if not from_free:
        points[FT] -= req.from_team_points
        points[TT] += req.from_team_points
    if not to_free:
        points[TT] -= req.to_team_points
        points[FT] += req.to_team_points

    # Log it
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append(
        f"On {now}, {FT} traded {req.drivers_from_team} +{req.from_team_points}pts "
        f"to {TT} for {req.drivers_to_team} +{req.to_team_points}pts."
    )

    # Persist
    locked.teams         = json.dumps(teams)
    locked.points        = json.dumps(points)
    locked.trade_history = json.dumps(history)
    db.commit()

    return {
        "message": "Locked‐season trade completed!",
        "trade_history": history
    }

@app.post("/update_race_points")
def update_race_points(season_id: str, race_id: str, db: Session = Depends(get_db)):
    locked = db.query(models.LockedSeason).filter(models.LockedSeason.season_id==season_id).first()
    if not locked:
        raise HTTPException(404, "Season not found.")
    processed = json.loads(locked.processed_races or "[]")
    if race_id in processed:
        raise HTTPException(400, "This race has already been processed.")

    # fetch from JOLPI endpoint
    resp = requests.get(
        f"https://api.jolpi.ca/ergast/f1/2025/{race_id}/results.json", timeout=10
    )
    if resp.status_code != 200:
        raise HTTPException(400, "Error fetching race data.")
    data = resp.json()
    try:
        results = data["MRData"]["RaceTable"]["Races"][0]["Results"]
    except (KeyError, IndexError):
        raise HTTPException(400, "No results for that race.")

    # compute driver→points
    driver_points = {}
    for r in results:
        name = f"{r['Driver']['givenName']} {r['Driver']['familyName']}"
        try:
            driver_points[name] = float(r["points"])
        except:
            driver_points[name] = 0.0

    teams      = json.loads(locked.teams)
    points     = json.loads(locked.points)
    rp         = json.loads(locked.race_points or "{}")

    # bank each drafted driver’s points
    for team_name, roster in teams.items():
        for driver in roster:
            pts = driver_points.get(driver, 0.0)
            rp.setdefault(race_id, {})[driver] = {"points": pts, "team": team_name}
            points[team_name] = points.get(team_name, 0) + pts

    processed.append(race_id)

    locked.points         = json.dumps(points)
    locked.race_points    = json.dumps(rp)
    locked.processed_races= json.dumps(processed)
    db.commit()

    return {"message": "Race points updated successfully.", "points": points}