"""
Unit tests for database models and CRUD operations.
Uses an in-memory SQLite database (no file I/O).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import models as _models  # noqa: F401 — register all ORM models
from backend.database.db import Base
from backend.database.models import Incident, User, Zone


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


class TestIncidentModel:
    def test_create_incident(self, db_session):
        inc = Incident(zone_name="Main Entrance", detection_type="animal", label="cat")
        db_session.add(inc)
        db_session.commit()
        assert inc.id is not None
        assert inc.zone_name == "Main Entrance"

    def test_to_dict_fields(self, db_session):
        inc = Incident(
            zone_name="Corridor",
            detection_type="person",
            label="person (blurred)",
            confidence=0.87,
        )
        db_session.add(inc)
        db_session.commit()
        d = inc.to_dict()
        assert "id" in d
        assert "timestamp" in d
        assert d["zone"] == "Corridor"
        assert d["detection_type"] == "person"
        assert d["confidence"] == pytest.approx(0.87, abs=0.001)

    def test_multiple_incidents_ordering(self, db_session):
        for label in ["cat", "dog", "motion"]:
            inc = Incident(zone_name="Backyard", detection_type="animal", label=label)
            db_session.add(inc)
        db_session.commit()
        results = db_session.query(Incident).all()
        assert len(results) == 3

    def test_default_status_is_open(self, db_session):
        inc = Incident(zone_name="Side Gate", detection_type="motion", label="motion")
        db_session.add(inc)
        db_session.commit()
        assert inc.status == "open"


class TestZoneModel:
    def test_create_zone(self, db_session):
        z = Zone(name="Test Zone", loitering_threshold_seconds=45)
        db_session.add(z)
        db_session.commit()
        assert z.id is not None
        d = z.to_dict()
        assert d["name"] == "Test Zone"
        assert d["loitering_threshold_seconds"] == 45

    def test_zone_tripwire_serialization(self, db_session):
        z = Zone(name="Gate")
        z.tripwire = [[0, 100], [640, 100]]
        db_session.add(z)
        db_session.commit()
        db_session.refresh(z)
        assert z.tripwire == [[0, 100], [640, 100]]


class TestUserModel:
    def test_create_user(self, db_session):
        u = User(
            username="alice",
            email="alice@test.com",
            hashed_password="hashed",
            role="viewer",
        )
        db_session.add(u)
        db_session.commit()
        assert u.id is not None
        d = u.to_dict()
        assert d["username"] == "alice"
        assert d["role"] == "viewer"
        assert "hashed_password" not in d
