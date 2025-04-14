from sqlalchemy import Column, Integer, String, Text
from database import Base

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    # Roster is stored as a JSON-encoded string, e.g. '["Driver1", "Driver2", ...]'
    roster = Column(Text, nullable=False)
    # Points is an integer total for the team (used during the draft phase)
    points = Column(Integer, default=0, nullable=False)

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    # drafted_by will hold the team name that drafted the driver (if any)
    drafted_by = Column(String(50), nullable=True)

class LockedSeason(Base):
    __tablename__ = "locked_seasons"
    id = Column(Integer, primary_key=True, index=True)
    # A unique identifier for the season – typically a UUID string
    season_id = Column(String(36), unique=True, nullable=False)
    # Stored as JSON: a mapping of team names to their rosters (lists of driver names)
    teams = Column(Text, nullable=False)
    # Stored as JSON: a mapping of team names to their cumulative points (numbers)
    points = Column(Text, nullable=False)
    # Stored as JSON: an array logging the trade history (each entry as a string)
    trade_history = Column(Text, nullable=False)
    # Stored as JSON: a mapping of race names (or IDs) to detailed race results. 
    # Example format:
    #   { "Bahrain": { "Oscar Piastri": {"points": 25, "team": "Tinsley Titters"}, ... }, ... }
    race_points = Column(Text, nullable=False)
    # Stored as JSON: an array of race IDs that have already been processed, so that the same race isn't updated twice.
    processed_races = Column(Text, nullable=False, default='[]')