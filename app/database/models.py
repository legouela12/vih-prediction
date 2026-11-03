from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, JSON, Text
from sqlalchemy.sql import func
from app.database.connection import Base


class PredictionLog(Base):
    __tablename__ = 'prediction_logs'

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    age_diagnostic = Column(Float, nullable=False)
    cd4_debut = Column(Integer, nullable=False)
    score_inf_opp = Column(Float, nullable=False)
    temps_suivi = Column(Float, nullable=False)

    stade_avance = Column(Boolean, nullable=False, default=False)
    non_observant = Column(Boolean, nullable=False, default=False)
    hospitalisation = Column(Boolean, nullable=False, default=False)
    tuberculoses = Column(Boolean, nullable=False, default=False)
    vit_seul = Column(Boolean, nullable=False, default=False)
    etude_secondaire_ou_plus = Column(Boolean, nullable=False, default=False)

    predicted_class = Column(String(128), nullable=False)
    confidence = Column(Float, nullable=False)
    probabilities = Column(JSON, nullable=False)
    risk_factors = Column(JSON, nullable=False)
    protective_factors = Column(JSON, nullable=False)
    clinical_alert = Column(String(256), nullable=True)
    interpretation = Column(Text, nullable=True)
    source = Column(String(128), nullable=False, default='frontend')
    raw_payload = Column(JSON, nullable=True)
