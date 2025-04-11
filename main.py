import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from datetime import datetime

# Get the database URL from your environment variable.
# Make sure you have set DATABASE_URL in your Render environment.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable is not set!")

# Create the SQLAlchemy engine
engine = create_engine(DATABASE_URL, echo=True)  # echo=True logs SQL; set to False in production.
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Declare the base for models
Base = declarative_base()

# ---------------------------
# Database Models
# ---------------------------
class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    points = Column(Integer, default=0)
    # Relationship to drivers
    drivers = relationship("TeamDriver", back_populates="team", cascade="all, delete-orphan")

class TeamDriver(Base):
    __tablename__ = "team_drivers"
    id = Column(Integer, primary_key=True, index=True)
    driver_name = Column(String, index=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    team_id = Column(Integer, ForeignKey("teams.id"))
    team = relationship("Team", back_populates="drivers")

# Create all tables (if they don't already exist)
Base.metadata.create_all(bind=engine)

# ---------------------------
# FastAPI App Setup
# ---------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust as needed; you can replace "*" with your allowed domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency: get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# Endpoints
# ---------------------------

@app.get("/")
def root():
    return {"message": "F1 Fantasy Backend Running with Persistent Storage"}

@app.get("/register_team")
def register_team(team_name: str, db: Session = Depends(get_db)):
    # Check if the team already exists.
    existing = db.query(Team).filter(Team.name == team_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team name already exists")
    new_team = Team(name=team_name)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return {"message": f"{team_name} registered successfully!"}

@app.get("/get_registered_teams")
def get_registered_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    result = {}
    for team in teams:
        # For each team, list the driver names in its roster.
        result[team.name] = [driver.driver_name for driver in team.drivers]
    return {"teams": result}

@app.post("/draft_driver")
def draft_driver(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if len(team.drivers) >= 6:
        raise HTTPException(status_code=400, detail="Team already has 6 drivers")

    # Check if the driver is already drafted in any team.
    existing_driver = db.query(TeamDriver).filter(TeamDriver.driver_name == driver_name).first()
    if existing_driver:
        raise HTTPException(status_code=400, detail="Driver already drafted")

    new_driver = TeamDriver(driver_name=driver_name, team=team)
    db.add(new_driver)
    db.commit()
    return {"message": f"{driver_name} drafted by {team_name}!"}

@app.post("/undo_draft")
def undo_draft(team_name: str, driver_name: str, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    driver = db.query(TeamDriver).filter(TeamDriver.team_id == team.id, TeamDriver.driver_name == driver_name).first()
    if not driver:
        raise HTTPException(status_code=400, detail="Driver not on team")
    db.delete(driver)
    db.commit()
    return {"message": f"{driver_name} removed from {team_name}"}

@app.post("/reset_teams")
def reset_teams(db: Session = Depends(get_db)):
    db.query(TeamDriver).delete()
    db.query(Team).delete()
    db.commit()
    return {"message": "All teams reset and data cleared!"}

# ---------------------------
# Future Steps: Lock Season, Trades, etc.
# ---------------------------
# You would add additional endpoints here (e.g., /lock_teams, /trade_locked) using similar patterns.