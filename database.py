import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Retrieve your Neon connection string from the environment.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable is not set.")

# Create the SQLAlchemy engine.
# Neon requires SSL, so we enforce that with "sslmode": "require".
# Added pool_recycle=3600 to recycle connections after 1 hour.
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},
    pool_recycle=3600,
    pool_pre_ping=True  # ping connections before use to prevent stale/EOF errors
)

# Create a configured "Session" class.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our ORM models.
Base = declarative_base()