"""
Integration tests for the FastAPI REST endpoints.
Uses TestClient with an in-memory SQLite database + StaticPool.
All protected routes are tested with a seeded admin user and valid JWT.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth.jwt_handler import create_access_token, hash_password
from backend.database import models as _models_import  # noqa: F401 — registers ORM models
from backend.database.db import Base, get_db
from backend.database.models import Incident, User, Zone
from backend.main import app

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture
def admin_user(db):
    user = User(
        username="testadmin",
        email="admin@test.com",
        hashed_password=hash_password("testpass"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def viewer_user(db):
    user = User(
        username="testviewer",
        email="viewer@test.com",
        hashed_password=hash_password("testpass"),
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user):
    return create_access_token(admin_user.id, admin_user.role)


@pytest.fixture
def viewer_token(viewer_user):
    return create_access_token(viewer_user.id, viewer_user.role)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def zone(db):
    z = Zone(name="Test Zone", loitering_threshold_seconds=30)
    db.add(z)
    db.commit()
    db.refresh(z)
    return z


@pytest.fixture
def seeded_incidents(db, zone):
    for dtype, label in [("animal", "cat"), ("person", "person (blurred)"), ("motion", "motion")]:
        db.add(Incident(zone_id=zone.id, zone_name=zone.name, detection_type=dtype, label=label, confidence=0.75))
    db.commit()


# ── Health ────────────────────────────────────────────────────────────────
class TestHealth:
    def test_health_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────────────────────────────────
class TestAuth:
    def test_login_success(self, client, admin_user):
        res = client.post("/auth/login", json={"username": "testadmin", "password": "testpass"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client, admin_user):
        res = client.post("/auth/login", json={"username": "testadmin", "password": "wrong"})
        assert res.status_code == 401

    def test_me_returns_user(self, client, admin_user, admin_token):
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["username"] == "testadmin"

    def test_protected_route_rejects_no_token(self, client):
        res = client.get("/api/incidents")
        assert res.status_code == 401  # HTTPBearer auto_error=False → 401 from dependency

    def test_viewer_cannot_access_admin_route(self, client, viewer_user, viewer_token):
        res = client.get("/api/users", headers={"Authorization": f"Bearer {viewer_token}"})
        assert res.status_code == 403


# ── Incidents ─────────────────────────────────────────────────────────────
class TestIncidents:
    def test_list_empty(self, client, admin_token):
        res = client.get("/api/incidents", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["total"] == 0

    def test_list_after_seed(self, client, admin_token, seeded_incidents):
        res = client.get("/api/incidents", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.json()["total"] == 3

    def test_filter_by_type(self, client, admin_token, seeded_incidents):
        res = client.get("/api/incidents?detection_type=animal",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.json()["total"] == 1

    def test_get_single(self, client, admin_token, seeded_incidents):
        res = client.get("/api/incidents/1", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["id"] == 1

    def test_404_on_missing(self, client, admin_token):
        res = client.get("/api/incidents/9999", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 404


# ── Stats ─────────────────────────────────────────────────────────────────
class TestStats:
    def test_stats_empty(self, client, admin_token):
        res = client.get("/api/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["total"] == 0

    def test_stats_after_seed(self, client, admin_token, seeded_incidents):
        res = client.get("/api/stats?hours=8760", headers={"Authorization": f"Bearer {admin_token}"})
        data = res.json()
        assert data["total"] == 3
        assert data["by_type"]["animal"] == 1


# ── Zones ─────────────────────────────────────────────────────────────────
class TestZones:
    def test_create_zone(self, client, admin_token):
        res = client.post("/api/zones", json={"name": "New Zone"},
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 201
        assert res.json()["name"] == "New Zone"

    def test_viewer_can_list_zones(self, client, viewer_token, zone):
        res = client.get("/api/zones", headers={"Authorization": f"Bearer {viewer_token}"})
        assert res.status_code == 200

    def test_viewer_cannot_create_zone(self, client, viewer_token):
        res = client.post("/api/zones", json={"name": "Viewer Zone"},
                          headers={"Authorization": f"Bearer {viewer_token}"})
        assert res.status_code == 403


# ── Heatmap ───────────────────────────────────────────────────────────────
class TestHeatmap:
    def test_heatmap_after_seed(self, client, admin_token, seeded_incidents):
        res = client.get("/api/heatmap?hours=8760",
                         headers={"Authorization": f"Bearer {admin_token}"})
        data = res.json()
        assert "Test Zone" in data
        assert data["Test Zone"]["total"] == 3
