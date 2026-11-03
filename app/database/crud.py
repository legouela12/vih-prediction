from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from app.database.models import PredictionLog
import json


def create_prediction_log(db: Session, log_data: dict) -> PredictionLog:
    """Crée un log de prédiction avec conversion JSON"""
    
    # Copier les données
    data = log_data.copy()
    
    # Convertir les dicts et listes en JSON
    if 'probabilities' in data and isinstance(data['probabilities'], dict):
        data['probabilities'] = json.dumps(data['probabilities'], ensure_ascii=False)
    
    if 'risk_factors' in data and isinstance(data['risk_factors'], list):
        data['risk_factors'] = json.dumps(data['risk_factors'], ensure_ascii=False)
    
    if 'protective_factors' in data and isinstance(data['protective_factors'], list):
        data['protective_factors'] = json.dumps(data['protective_factors'], ensure_ascii=False)
    
    if 'raw_payload' in data and isinstance(data['raw_payload'], dict):
        data['raw_payload'] = json.dumps(data['raw_payload'], ensure_ascii=False)
    
    # Créer l'enregistrement
    prediction_log = PredictionLog(**data)
    db.add(prediction_log)
    db.commit()
    db.refresh(prediction_log)
    return prediction_log


def get_dashboard_stats(db: Session) -> dict:
    total_predictions = db.query(func.count(PredictionLog.id)).scalar() or 0
    average_confidence = float(db.query(func.avg(PredictionLog.confidence)).scalar() or 0.0)
    low_confidence_count = db.query(func.count(PredictionLog.id)).filter(PredictionLog.confidence < 0.5).scalar() or 0

    predictions_by_class = [
        {"prediction": row[0], "count": row[1]}
        for row in db.query(PredictionLog.predicted_class, func.count(PredictionLog.id))
                     .group_by(PredictionLog.predicted_class)
                     .all()
    ]

    latest_predictions = [
        {
            "created_at": item.created_at.isoformat(),
            "prediction": item.predicted_class,
            "confidence": float(item.confidence),
            "age_diagnostic": item.age_diagnostic,
            "cd4_debut": item.cd4_debut,
        }
        for item in db.query(PredictionLog)
                      .order_by(desc(PredictionLog.created_at))
                      .limit(5)
                      .all()
    ]

    return {
        "total_predictions": total_predictions,
        "average_confidence": average_confidence,
        "low_confidence_count": low_confidence_count,
        "predictions_by_class": predictions_by_class,
        "latest_predictions": latest_predictions,
    }