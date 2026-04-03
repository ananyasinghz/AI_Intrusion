from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables. Used for development; production uses Alembic migrations."""
    from backend.database import models  # noqa: F401 — registers all ORM models
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_default_zones(db: Session) -> None:
    """Insert default zones on first run if the zones table is empty."""
    from backend.config import ZONES
    from backend.database.models import Zone

    if db.query(Zone).count() > 0:
        return

    for name in ZONES:
        db.add(Zone(name=name, loitering_threshold_seconds=30))
    db.commit()


def seed_admin_user(db: Session) -> None:
    """Create a default admin user on first run if no users exist."""
    from backend.database.models import User

    if db.query(User).count() > 0:
        return

    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    admin = User(
        username="admin",
        email="admin@intrusion.local",
        hashed_password=pwd_context.hash("changeme"),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
