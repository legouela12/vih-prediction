from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict
import time

router = APIRouter()

# Instance globale du service ML (sera définie dans main.py)
ml_service_instance = None

# Modèles Pydantic pour les requêtes/réponses
class PatientInput(BaseModel):
    age_diagnostic: int = Field(..., ge=0, le=120, example=28)
    cd4_debut: int = Field(..., ge=0, le=2000, example=350)
    score_inf_opp: float = Field(..., ge=0, le=100, example=12.5)
    temps_suivi: int = Field(..., ge=0, example=730)
    stade_avance: bool = False
    non_observant: bool = False
    hospitalisation: bool = False
    tuberculoses: bool = False
    vit_seul: bool = True
    etude_secondaire_ou_plus: bool = True

class PredictionResponse(BaseModel):
    success: bool = True
    prediction: str
    confidence: float
    probabilities: Dict[str, float]
    processing_time_ms: int

class ModelInfoResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_name: str
    model_type: str
    classes: List[str]
    features: List[str]
    n_features: int
    version: str

def get_ml_service():
    global ml_service_instance
    if ml_service_instance is None:
        raise HTTPException(status_code=503, detail="Service ML non initialisé")
    if ml_service_instance.prediction_pipeline is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return ml_service_instance

@router.post("/predict", response_model=PredictionResponse)
async def predict_patient(
    patient: PatientInput,
    ml_service = Depends(get_ml_service)
):
    """Prédiction pour un patient"""
    start_time = time.time()
    
    try:
        predicted_class, probabilities = ml_service.predict(patient.dict())
        processing_time = int((time.time() - start_time) * 1000)
        
        return PredictionResponse(
            success=True,
            prediction=predicted_class,
            confidence=max(probabilities.values()),
            probabilities=probabilities,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.post("/predict/batch")
async def predict_batch(
    patients: List[PatientInput],
    ml_service = Depends(get_ml_service)
):
    """Prédiction pour plusieurs patients (max 50)"""
    if len(patients) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 patients par batch")
    
    start_time = time.time()
    results = ml_service.predict_batch([p.dict() for p in patients])
    processing_time = int((time.time() - start_time) * 1000)
    
    return {
        "success": True,
        "count": len(results),
        "results": results,
        "processing_time_ms": processing_time
    }

@router.get("/model/info", response_model=ModelInfoResponse)
async def get_model_info(ml_service = Depends(get_ml_service)):
    info = ml_service.get_model_info()
    return ModelInfoResponse(**info)

@router.get("/model/health")
async def model_health(ml_service = Depends(get_ml_service)):
    return {
        "status": "healthy",
        "model_loaded": ml_service.prediction_pipeline is not None,
        "classes": ml_service.classes_.tolist() if ml_service.classes_ is not None else None
    }

# ⚠️ Endpoint /features/importance SUPPRIMÉ (non nécessaire pour votre besoin)