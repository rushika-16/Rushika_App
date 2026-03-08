import os
from sqlmodel import SQLModel, create_engine, Session

# SQLite database file
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./credit_card.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session