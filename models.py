from sqlalchemy import Column, Integer, String, Text
from database import Base

# Team model
class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    # Store the roster as a JSON string (an array of driver names)
    roster = Column(Text, nullable=False)
    points = Column(Integer, default=0, nullable=False)

# Driver model
class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    # Driver name, e.g., "Max Verstappen"
    name = Column(String(100), unique=True, nullable=False)
    # The team that drafted the driver (optional); store as string
    drafted_by = Column(String(50), nullable=True)

# LockedSeason model
class LockedSeason(Base):
    __tablename__ = "locked_seasons"
    id = Column(Integer, primary_key=True, index=True)
    # Unique identifier for the season
    season_id = Column(String(36), unique=True, nullable=False)
    # JSON string representing teams and their rosters, e.g., {"TeamA": [...], "TeamB": [...]}
    teams = Column(Text, nullable=False)
    # JSON string for points per team, e.g., {"TeamA": 0, "TeamB": 0}
    points = Column(Text, nullable=False)
    # JSON string for trade history (an array of strings)
    trade_history = Column(Text, nullable=False)