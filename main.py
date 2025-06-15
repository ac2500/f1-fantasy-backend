# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uuid
import json
from typing import List
from datetime import datetime

# —— Add the F1 rounds mapping here ——
RACE_LIST = [
    "Bahrain","Saudi Arabia","Miami","Imola",
    "Monaco","Spain","Canada","Austria",
    "UK","Belgium","Hungary","Netherlands",
    "Monza","Azerbaijan","Singapore","Texas",
    "Mexico","Brazil","Vegas","Qatar",
    "Abu Dhabi"
]

ROUND_MAP = {
    "Bahrain":4,   "Saudi Arabia":5,   "Miami":6,   "Imola":7,
    "Monaco":8,    "Spain":9,          "Canada":10, "Austria":11,
    "UK":12,       "Belgium":13,       "Hungary":14,"Netherlands":15,
    "Monza":16,    "Azerbaijan":17,    "Singapore":18,"Texas":19,
    "Mexico":20,   "Brazil":21,        "Vegas":22,  "Qatar":23,
    "Abu Dhabi":24
}
# ————————————————————————————————
# main.py (somewhere near the top, just below ROUND_MAP)

BONUS_MAP = {
    11: 0.50,
    12: 0.40,
    13: 0.30,
    14: 0.20,
    15: 0.10,
    16: 0.05,
    17: 0.04,
    18: 0.03,
    19: 0.02,
    20: 0.01,
}

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
    """
    Return the locked season’s state, including:
      - teams & their rosters
      - total team points
      - trade history
      - which races have been processed
      - per-race, per-driver points (race_points)
    """
    locked = (
        db.query(models.LockedSeason)
          .filter(models.LockedSeason.season_id == season_id)
          .first()
    )
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")

    # load all JSON blobs
    teams           = json.loads(locked.teams           or "{}")
    points          = json.loads(locked.points          or "{}")
    trade_history   = json.loads(locked.trade_history   or "[]")
    processed_races = json.loads(locked.processed_races or "[]")
    race_points     = json.loads(locked.race_points     or "{}")

    return {
        "teams":           teams,
        "points":          points,
        "trade_history":   trade_history,
        "processed_races": processed_races,
        "race_points":     race_points,   # ← this was missing
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
    locked = (
        db.query(models.LockedSeason)
          .filter(models.LockedSeason.season_id == season_id)
          .first()
    )
    if not locked:
        raise HTTPException(404, "Season not found.")

    # 1) Load structures
    teams       = json.loads(locked.teams or "{}")       # { teamName: [driver,…] }
    free_agents = json.loads(locked.free_agents or "[]") # [ driver,… ]
    points      = json.loads(locked.points or "{}")
    history     = json.loads(locked.trade_history or "[]")

    # … your existing validation checks here …

    # 2) Remove from “from_team”
    if request.from_team == "__FREE_AGENCY__":
        for d in request.drivers_from_team:
            if d not in free_agents:
                raise HTTPException(400, detail=f"{d} not in free agency")
            free_agents.remove(d)
    else:
        roster = teams.get(request.from_team, [])
        for d in request.drivers_from_team:
            if d not in roster:
                raise HTTPException(
                    400, detail=f"{d} not on team {request.from_team}"
                )
            roster.remove(d)
        teams[request.from_team] = roster

    # 3) Remove from “to_team”
    if request.to_team == "__FREE_AGENCY__":
        for d in request.drivers_to_team:
            if d not in free_agents:
                raise HTTPException(400, detail=f"{d} not in free agency")
            free_agents.remove(d)
    else:
        roster = teams.get(request.to_team, [])
        for d in request.drivers_to_team:
            if d not in roster:
                raise HTTPException(
                    400, detail=f"{d} not on team {request.to_team}"
                )
            roster.remove(d)
        teams[request.to_team] = roster

    # 4) Add into the opposite side
    if request.to_team == "__FREE_AGENCY__":
        free_agents.extend(request.drivers_from_team)
    else:
        teams.setdefault(request.to_team, []).extend(request.drivers_from_team)

    if request.from_team == "__FREE_AGENCY__":
        free_agents.extend(request.drivers_to_team)
    else:
        teams.setdefault(request.from_team, []).extend(request.drivers_to_team)

    # 5) Sweetener point exchange
    points.setdefault(request.from_team, 0.0)
    points.setdefault(request.to_team,   0.0)
    points[request.from_team] -= request.from_team_points
    points[request.to_team]   += request.from_team_points
    points[request.to_team]   -= request.to_team_points
    points[request.from_team] += request.to_team_points

    # 6) Log the trade
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append(
        f"On {time_str}, {request.from_team} traded {request.drivers_from_team} "
        f"+{request.from_team_points}pts to {request.to_team} for "
        f"{request.drivers_to_team} +{request.to_team_points}pts."
    )

    # 7) Persist all three blobs
    locked.teams         = json.dumps(teams)
    locked.free_agents  = json.dumps(free_agents)
    locked.points       = json.dumps(points)
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
    Update points for a given F1 round (race_id) in the locked fantasy season.
    Applies F1 API points 1–10, then custom 11→0.5, 12→0.4, …, 20→0.01.
    """
    # 1) Load the LockedSeason record
    locked = (
        db.query(models.LockedSeason)
        .filter(models.LockedSeason.season_id == season_id)
        .first()
    )
    if not locked:
        raise HTTPException(status_code=404, detail="Season not found.")

    # 2) Parse existing JSON blobs
    processed = json.loads(locked.processed_races or "[]")  # e.g. ["4","5","6","7"]
    pts_map   = json.loads(locked.points or "{}")          # {team: total}
    rp_data   = json.loads(locked.race_points or "{}")     # {"4":{...},"5":{...}, ...}
    teams     = json.loads(locked.teams or "{}")           # {team: [drivers...]}

# ← insert the “latest” block here ↓
    if race_id == "latest":
        next_round = None
        for name in RACE_LIST:
            rn = str(ROUND_MAP[name])
            if rn in processed:
                continue
            resp  = requests.get(
                f"https://api.jolpi.ca/ergast/f1/2025/{rn}/results.json", timeout=10
            )
            data  = resp.json()
            races = data["MRData"]["RaceTable"]["Races"]
            if not races:
                raise HTTPException(400, detail="Next race not yet available")
            next_round = rn
            break

        if next_round is None:
            raise HTTPException(400, detail="All races have been processed")
        race_id = next_round
    # ↑ end insertion

    # 3) Prevent double‐processing
    if race_id in processed:
        raise HTTPException(status_code=400, detail="This race has already been processed.")

    # 4) Fetch from Ergast via Jolpi
    resp = requests.get(
        f"https://api.jolpi.ca/ergast/f1/2025/{race_id}/results.json",
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Error fetching race data.")
    data = resp.json()

    # 5) Drill down to the Races array, bail out if empty
    races = data.get("MRData", {}) \
                .get("RaceTable", {}) \
                .get("Races", [])
    if not races:
        # no result yet for that round
        raise HTTPException(status_code=400, detail="No race data available for this round.")

    results = races[0].get("Results", [])

    # 6) Build driver→points mapping with your custom scoring
    driver_pts: Dict[str, float] = {}
    for r in results:
        pos    = int(r["position"])
        status = r.get("status","").lower()
        name   = f"{r['Driver']['givenName']} {r['Driver']['familyName']}"

        # 1) start with the official points (0 for P11+)
        pts = float(r.get("points", 0))

        # 2) only apply bonus if they actually finished/classified
        if pos in BONUS_MAP and status in ("finished", "classified", "lapped"):
            pts += BONUS_MAP[pos]

        # 3) round to two decimals to avoid float-weirdness
        pts = round(pts, 2)

        driver_pts[name] = pts

    # 7) Apply points to each rostered driver
    rp_data.setdefault(race_id, {})
    for team, roster in teams.items():
        pts_map.setdefault(team, 0.0)
        for drv in roster:
            p = driver_pts.get(drv, 0.0)
            rp_data[race_id][drv] = {"points": p, "team": team}
            pts_map[team] += p

    # 8) Mark this round as processed **after** successful application
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