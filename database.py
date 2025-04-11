import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Retrieve your Neon connection string from the environment
DATABASE_URL = os.getenv("NEON_DB_URL")
if not DATABASE_URL:
    raise Exception("NEON_DB_URL environment variable is not set.")

# Create the SQLAlchemy engine.
# Neon requires SSL, so we enforce that with "sslmode": "require".
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"}
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our ORM models
Base = declarative_base()