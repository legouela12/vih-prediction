"""
Configuration des fixtures pour les tests pytest
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
from pathlib import Path

# Ajouter le backend au path
backend_path = Path(__file__).parent.parent
sys.path.append(str(backend_path))

from app.main import app
from app.database.connection import Base, get_db
from app.database.models import PredictionLog


# Base de données de test SQLite en mémoire
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Fixture pour une session de base de données de test"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Fixture pour le client de test FastAPI"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def sample_patient():
    """Fixture avec un patient exemple"""
    return {
        "age_diagnostic": 35,
        "cd4_debut": 450,
        "score_inf_opp": 0.0,
        "temps_suivi": 24,
        "stade_avance": False,
        "non_observant": False,
        "hospitalisation": False,
        "tuberculoses": False,
        "vit_seul": False,
        "etude_secondaire_ou_plus": True
    }


@pytest.fixture(scope="session")
def high_risk_patient():
    """Fixture avec un patient à haut risque"""
    return {
        "age_diagnostic": 60,
        "cd4_debut": 150,
        "score_inf_opp": 3.0,
        "temps_suivi": 3,
        "stade_avance": True,
        "non_observant": True,
        "hospitalisation": True,
        "tuberculoses": True,
        "vit_seul": True,
        "etude_secondaire_ou_plus": False
    }


@pytest.fixture(scope="session")
def good_prognosis_patient():
    """Fixture avec un patient à bon pronostic"""
    return {
        "age_diagnostic": 25,
        "cd4_debut": 800,
        "score_inf_opp": 0.0,
        "temps_suivi": 60,
        "stade_avance": False,
        "non_observant": False,
        "hospitalisation": False,
        "tuberculoses": False,
        "vit_seul": False,
        "etude_secondaire_ou_plus": True
    }