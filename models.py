from sqlalchemy import Column, Integer, String, Text
from database import Base

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    # The roster is stored as a JSON string (e.g., '["Driver1", "Driver2", ...]')
    roster = Column(Text, nullable=False)
    points = Column(Integer, default=0, nullable=False)

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    # drafted_by stores the team name that drafted the driver (if any)
    drafted_by = Column(String(50), nullable=True)

class LockedSeason(Base):
    __tablename__ = "locked_seasons"
    id = Column(Integer, primary_key=True, index=True)
    # A unique identifier for the season (as a string, e.g., a UUID)
    season_id = Column(String(36), unique=True, nullable=False)
    # Teams data stored as a JSON string (e.g., {"TeamA": ["Driver1", "Driver2", ...], ...})
    teams = Column(Text, nullable=False)
    # Points data stored as a JSON string (e.g., {"TeamA": 50, "TeamB": 20, ...})
    points = Column(Text, nullable=False)
    # Trade history stored as a JSON string (e.g., an array of strings that log each trade or update)
    trade_history = Column(Text, nullable=False)
    # Processed race IDs stored as a JSON string, to ensure the same race isn't processed twice.
    processed_races = Column(Text, nullable=False, default='[]')