from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from typing import Optional
from app.api import predict, visualizations
from app.api.metrics import router as metrics_router
from app.api.auth_2fa import router as auth_2fa_router  # ⭐ ICI
from app.services.ml_service import MLService
from app.database.connection import engine, Base, get_db
from app.database.models import PredictionLog
from app.api.visualizations import PatientInput
from datetime import datetime
import json
from pydantic import BaseModel
from app.auth.jwt_handler import authenticate_user, create_access_token, get_current_user, require_role
from app.api.openmrs import router as openmrs_router
from app.services.openmrs_client import OpenMRSClient

# ============================================================================
# ⚠️ SUPPRIMER CETTE LIGNE ICI (app.include_router avant app = FastAPI())
# ============================================================================
# app.include_router(auth_2fa_router, prefix="/api/auth", tags=["authentification"])
# ⚠️ DÉPLACER PLUS BAS

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

ml_service = None

# ============================================================================
# MODÈLES POUR L'AUTHENTIFICATION
# ============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str
    code_2fa: Optional[str] = None  

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str
    full_name: str

class UserInfo(BaseModel):
    username: str
    role: str
    email: str
    full_name: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_service
    
    print("=" * 60)
    print("🚀 Démarrage de l'API VIH Prediction")
    print("=" * 60)
    
    # Vérification du dossier static
    static_dir = BASE_DIR / "static"
    if not static_dir.exists():
        static_dir.mkdir(exist_ok=True)
        print("📁 Dossier static créé")
    
    plots_dir = static_dir / "plots"
    if not plots_dir.exists():
        plots_dir.mkdir(parents=True, exist_ok=True)
        print("📁 Dossier static/plots créé")
    
    ml_service = MLService()
    try:
        ml_service.load_models()
        print("✅ Modèle chargé avec succès")
        
        # Vérification que les instances sont bien partagées
        app.state.ml_service = ml_service
        predict.ml_service_instance = ml_service
        visualizations.ml_service_instance = ml_service
        
        # Informations sur le modèle
        if ml_service.prediction_pipeline:
            model_info = ml_service.get_model_info()
            print(f"📊 Modèle: {model_info.get('model_name', 'Unknown')}")
            print(f"📊 Classes: {model_info.get('classes', [])}")
            print(f"📊 Features: {len(model_info.get('features', []))}")
        
        # ========== AJOUTER ICI ==========
        openmrs_client = OpenMRSClient(
            base_url=os.getenv("OPENMRS_BASE_URL", "http://localhost:8083/openmrs/ws/rest/v1"),
            username=os.getenv("OPENMRS_USERNAME", "admin"),
            password=os.getenv("OPENMRS_PASSWORD", "Admin123"),
            timeout=float(os.getenv("OPENMRS_TIMEOUT", "10"))
        )
        app.state.openmrs_client = openmrs_client
        openmrs_status = openmrs_client.check_connection()
        if openmrs_status.get("authenticated"):
            print(f"✅ Connecté à OpenMRS : {openmrs_client.base_url}")
        else:
            print(f"⚠️ OpenMRS indisponible ou non authentifié : {openmrs_status.get('error', 'identifiants refusés')}")
        # ========== FIN AJOUT ==========

        print("=" * 60)
        Base.metadata.create_all(bind=engine)
        print("✅ Tables de base de données créées ou vérifiées")
        print("✅ API prête à recevoir des requêtes")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Erreur lors du chargement: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    yield
    
    print("=" * 60)
    print("👋 Arrêt de l'API...")
    print("=" * 60)


# ============================================================================
# CRÉER L'APPLICATION FASTAPI
# ============================================================================

app = FastAPI(
    title="VIH Prediction API",
    description="API de prédiction du devenir des patients VIH - Aide à la décision clinique",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================================================
# CONFIGURATION CORS
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ============================================================================
# SERVEUR STATIQUE
# ============================================================================

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ============================================================================
# INCLUSION DES ROUTES ⭐ TOUTES LES ROUTES ICI
# ============================================================================

app.include_router(predict.router, prefix="/api", tags=["prediction"])
app.include_router(visualizations.router, prefix="/api", tags=["visualizations"])
app.include_router(metrics_router, prefix="/api", tags=["metrics"])
app.include_router(auth_2fa_router, prefix="/api/auth", tags=["authentification"])  # ⭐ ICI
app.include_router(openmrs_router, prefix="/api", tags=["openmrs"])


@app.get("/openmrs-predict/{patient_uuid}")
async def openmrs_predict_compat(patient_uuid: str, request: Request):
    """Compat: ancienne route externe -> redirige vers `/api/predict-from-openmrs/{patient_uuid}`"""
    from fastapi.responses import RedirectResponse
    # utilise le nom d'endpoint défini dans `app.api.openmrs` pour construire l'URL
    try:
        target = app.router.url_path_for("predict_from_openmrs", patient_uuid=patient_uuid)
    except Exception:
        target = f"/api/predict-from-openmrs/{patient_uuid}"
    return RedirectResponse(url=target)

# ============================================================================
# ROUTES
# ============================================================================

# Route pour les fichiers statiques générés
@app.get("/static/{filepath:path}")
async def serve_static(filepath: str):
    """Servir les fichiers statiques (images, etc.)"""
    from fastapi.responses import FileResponse
    file_path = Path("static") / filepath
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Fichier non trouvé")


@app.get("/")
async def root():
    """Route racine avec informations API"""
    
    model_status = {
        "loaded": ml_service is not None and ml_service.prediction_pipeline is not None,
        "classes": None,
        "features_count": None
    }
    
    if model_status["loaded"]:
        try:
            model_info = ml_service.get_model_info()
            model_status["classes"] = model_info.get("classes", [])
            model_status["features_count"] = model_info.get("n_features", 0)
        except:
            pass
    
    return {
        "message": "VIH Prediction API - Aide à la décision clinique",
        "status": "operational",
        "version": "2.0.0",
        "model_loaded": model_status["loaded"],
        "model_info": {
            "classes": model_status.get("classes", []),
            "n_features": model_status.get("features_count", 0)
        } if model_status["loaded"] else None,
        "endpoints": {
            "prediction": {
                "single": "POST /api/predict",
                "batch": "POST /api/predict/batch",
                "validate": "POST /api/predict/validate-only",
                "debug": "POST /api/predict/debug"
            },
            "model": {
                "info": "GET /api/model/info",
                "health": "GET /api/model/health",
                "decision_guide": "GET /api/viz/decision-guide"
            },
            "visualizations": {
                "ui": "GET /api/predict-ui",
                "dashboard": "GET /api/viz/dashboard",
                "dashboard_crud": "GET /api/dashboard-crud",
                "feature_importance": "GET /api/viz/feature-importance",
                "roc_curve": "GET /api/viz/roc-curve",
                "dca_curve": "GET /api/viz/dca-curve",
                "confusion_matrix": "GET /api/viz/confusion-matrix",
                "shap_summary": "GET /api/viz/shap-summary",
                "shap_explain": "POST /api/viz/shap-explain"
            },
            "crud": {
                "list": "GET /api/predictions",
                "detail": "GET /api/predictions/{id}",
                "create": "POST /api/predictions",
                "delete": "DELETE /api/predictions/{id}",
                "stats": "GET /api/predictions/stats"
            },
            "export": {
                "csv_json": "GET /api/export/predictions"
            },
            "documentation": {
                "swagger": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json"
            }
        },
        "clinical_warning": "⚠️ Outil d'aide à la décision - Validation clinique requise. Performance limitée pour la classe 'Transféré'.",
        "usage": {
            "predict_ui": "http://localhost:8000/api/predict-ui",
            "dashboard_crud": "http://localhost:8000/api/dashboard-crud",
            "dashboard": "http://localhost:8000/api/viz/dashboard",
            "docs": "http://localhost:8000/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Vérification de santé détaillée"""
    
    health_status = {
        "status": "healthy",
        "timestamp": None,
        "model": {
            "loaded": False,
            "pipeline_ready": False,
            "classes_ready": False
        },
        "components": {
            "static_dir": False,
            "plots_dir": False
        }
    }
    
    try:
        health_status["timestamp"] = datetime.now().isoformat()
        
        if ml_service is not None:
            health_status["model"]["loaded"] = True
            health_status["model"]["pipeline_ready"] = ml_service.prediction_pipeline is not None
            health_status["model"]["classes_ready"] = ml_service.classes_ is not None
            
            if health_status["model"]["pipeline_ready"]:
                health_status["model"]["classes"] = list(ml_service.class_mapping.values()) if hasattr(ml_service, 'class_mapping') else None
        
        health_status["components"]["static_dir"] = (BASE_DIR / "static").exists()
        health_status["components"]["plots_dir"] = (BASE_DIR / "static" / "plots").exists()
        
        if not health_status["model"]["pipeline_ready"]:
            health_status["status"] = "degraded"
            health_status["warning"] = "Modèle non chargé"
        
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
    
    return health_status


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Gestion élégante des erreurs de validation"""
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "Erreur de validation des données",
            "details": exc.errors(),
            "message": "Vérifiez que toutes les données sont au bon format"
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Gestion globale des exceptions"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Erreur interne du serveur",
            "message": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else "Contacter l'administrateur"
        }
    )


# ============================================================================
# ROUTES UTILITAIRES
# ============================================================================

@app.get("/test-static")
async def test_static():
    """Vérifie que les fichiers statiques sont accessibles"""
    from pathlib import Path
    static_dir = Path("static")
    plots_dir = static_dir / "plots"
    
    return {
        "static_dir_exists": static_dir.exists(),
        "static_dir_path": str(static_dir.absolute()),
        "plots_dir_exists": plots_dir.exists(),
        "plots_dir_path": str(plots_dir.absolute()),
        "files_in_plots": [f.name for f in plots_dir.glob("*.png")][:5] if plots_dir.exists() else []
    }


@app.get("/ping")
async def ping():
    """Test simple de connectivité"""
    return {"pong": True, "timestamp": __import__("time").time()}


# ============================================================================
# 📊 ENDPOINT D'EXPORT DES DONNÉES
# ============================================================================

@app.get("/api/export/predictions")
async def export_predictions(
    format: str = "csv",
    limit: int = 1000,
    prediction_class: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Exporte les prédictions en CSV ou JSON avec filtres optionnels
    """
    from fastapi.responses import Response
    from sqlalchemy import desc
    import io
    import csv
    
    query = db.query(PredictionLog)
    
    if prediction_class:
        query = query.filter(PredictionLog.predicted_class == prediction_class)
    
    if start_date:
        start_datetime = datetime.fromisoformat(start_date)
        query = query.filter(PredictionLog.created_at >= start_datetime)
    
    if end_date:
        end_datetime = datetime.fromisoformat(end_date)
        query = query.filter(PredictionLog.created_at <= end_datetime)
    
    predictions = query.order_by(desc(PredictionLog.created_at)).limit(limit).all()
    
    if format.lower() == "json":
        data = []
        for pred in predictions:
            data.append({
                "id": pred.id,
                "created_at": pred.created_at.isoformat() if pred.created_at else None,
                "age_diagnostic": pred.age_diagnostic,
                "cd4_debut": pred.cd4_debut,
                "score_inf_opp": pred.score_inf_opp,
                "temps_suivi": pred.temps_suivi,
                "stade_avance": pred.stade_avance,
                "non_observant": pred.non_observant,
                "hospitalisation": pred.hospitalisation,
                "tuberculoses": pred.tuberculoses,
                "vit_seul": pred.vit_seul,
                "etude_secondaire_ou_plus": pred.etude_secondaire_ou_plus,
                "predicted_class": pred.predicted_class,
                "confidence": pred.confidence,
                "risk_factors": pred.risk_factors,
                "protective_factors": pred.protective_factors,
                "clinical_alert": pred.clinical_alert,
                "interpretation": pred.interpretation,
                "source": pred.source
            })
        
        filename = f"predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            content=json.dumps(data, indent=2, ensure_ascii=False, default=str),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    else:
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        
        writer.writerow([
            "ID", "Date", "Âge", "CD4", "Score IO", "Suivi (mois)",
            "Stade avancé", "Non-observant", "Hospitalisation", "Tuberculose",
            "Vit seul", "Étude secondaire+", "Prédiction", "Confiance (%)",
            "Facteurs risque", "Facteurs protecteurs", "Alerte clinique", "Source"
        ])
        
        for pred in predictions:
            clinical_alert_clean = ""
            if pred.clinical_alert:
                clinical_alert_clean = pred.clinical_alert.replace('\n', ' ').replace('\r', ' ')
                if len(clinical_alert_clean) > 150:
                    clinical_alert_clean = clinical_alert_clean[:150] + "..."
            
            writer.writerow([
                pred.id,
                pred.created_at.strftime("%Y-%m-%d %H:%M:%S") if pred.created_at else "",
                pred.age_diagnostic,
                pred.cd4_debut,
                pred.score_inf_opp,
                pred.temps_suivi,
                "Oui" if pred.stade_avance else "Non",
                "Oui" if pred.non_observant else "Non",
                "Oui" if pred.hospitalisation else "Non",
                "Oui" if pred.tuberculoses else "Non",
                "Oui" if pred.vit_seul else "Non",
                "Oui" if pred.etude_secondaire_ou_plus else "Non",
                pred.predicted_class,
                f"{pred.confidence * 100:.1f}",
                ", ".join(pred.risk_factors) if pred.risk_factors else "",
                ", ".join(pred.protective_factors) if pred.protective_factors else "",
                clinical_alert_clean,
                pred.source or "api"
            ])
        
        content = output.getvalue()
        content_utf8_bom = '\uFEFF' + content
        
        filename = f"predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=content_utf8_bom.encode('utf-8'),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


# ============================================================================
# 📊 ENDPOINTS CRUD POUR LE DASHBOARD
# ============================================================================

@app.get("/api/predictions/stats")
async def get_prediction_stats(db: Session = Depends(get_db)):
    """Récupère les statistiques pour le dashboard"""
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    by_class = db.query(
        PredictionLog.predicted_class,
        func.count(PredictionLog.id).label('count')
    ).group_by(PredictionLog.predicted_class).all()
    
    trend = []
    for i in range(6, -1, -1):
        date = datetime.now() - timedelta(days=i)
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = db.query(PredictionLog).filter(
            PredictionLog.created_at >= date_start,
            PredictionLog.created_at <= date_end
        ).count()
        trend.append({
            "date": date.strftime("%Y-%m-%d"),
            "count": count
        })
    
    valid_classes = []
    for c in by_class:
        if c[0] is not None:
            valid_classes.append({"name": c[0], "count": c[1]})
    
    return {
        "by_class": valid_classes,
        "trend": trend
    }


@app.get("/api/predictions/{prediction_id}")
async def get_prediction_detail(prediction_id: int, db: Session = Depends(get_db)):
    """Récupère les détails d'une prédiction"""
    prediction = db.query(PredictionLog).filter(PredictionLog.id == prediction_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prédiction non trouvée")
    
    # Convertir les données JSON
    pred_dict = prediction.__dict__.copy()
    if '_sa_instance_state' in pred_dict:
        del pred_dict['_sa_instance_state']
    
    return {"success": True, "data": pred_dict}


@app.get("/api/predictions")
async def get_predictions(
    page: int = 1,
    limit: int = 20,
    prediction_class: Optional[str] = None,
    date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Récupère la liste des prédictions avec pagination"""
    from sqlalchemy import func, desc
    from datetime import datetime
    
    query = db.query(PredictionLog)
    
    if prediction_class:
        query = query.filter(PredictionLog.predicted_class == prediction_class)
    
    if date:
        target_date = datetime.fromisoformat(date)
        query = query.filter(func.date(PredictionLog.created_at) == target_date.date())
    
    total = query.count()
    offset = (page - 1) * limit
    predictions = query.order_by(desc(PredictionLog.created_at)).offset(offset).limit(limit).all()
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(PredictionLog).filter(PredictionLog.created_at >= today_start).count()
    low_confidence_count = db.query(PredictionLog).filter(PredictionLog.confidence < 0.5).count()
    
    predictions_data = []
    for p in predictions:
        pred_dict = {
            "id": p.id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "age_diagnostic": p.age_diagnostic,
            "cd4_debut": p.cd4_debut,
            "score_inf_opp": p.score_inf_opp,
            "temps_suivi": p.temps_suivi,
            "stade_avance": p.stade_avance,
            "non_observant": p.non_observant,
            "hospitalisation": p.hospitalisation,
            "tuberculoses": p.tuberculoses,
            "vit_seul": p.vit_seul,
            "etude_secondaire_ou_plus": p.etude_secondaire_ou_plus,
            "predicted_class": p.predicted_class,
            "confidence": p.confidence,
            "source": p.source
        }
        predictions_data.append(pred_dict)
    
    return {
        "success": True,
        "data": predictions_data,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if total > 0 else 1,
        "stats": {
            "total": total,
            "today": today_count,
            "low_confidence": low_confidence_count
        }
    }

@app.post("/api/predictions")
async def create_prediction(
    patient: PatientInput,
    db: Session = Depends(get_db)
):
    """Crée une nouvelle prédiction avec calcul des facteurs de risque"""
    from app.services.ml_service import MLService
    from app.api.visualizations import FEATURE_NAMES_FR
    import json
    import pandas as pd
    import shap
    
    ml_service_instance = MLService()
    ml_service_instance.load_models()
    
    # Convertir les données
    patient_dict = patient.dict()
    input_to_model_mapping = {
        'age_diagnostic': 'Age_diagnostic',
        'cd4_debut': 'CD4_debut',
        'score_inf_opp': 'Score_inf_opp',
        'temps_suivi': 'temps_suivi',
        'stade_avance': 'Stade_avance',
        'non_observant': 'Non_observant',
        'hospitalisation': 'Hospitalisation',
        'tuberculoses': 'Tuberculoses',
        'vit_seul': 'Vit_seul',
        'etude_secondaire_ou_plus': 'Etude_secondaire_ou_plus'
    }
    
    normalized_dict = {}
    for key, value in patient_dict.items():
        model_key = input_to_model_mapping.get(key, key)
        normalized_dict[model_key] = value
    
    # Prédiction
    predicted_class, probabilities = ml_service_instance.predict(normalized_dict)
    confidence = max(probabilities.values())
    
    # Convertir probabilities en JSON
    probabilities_json = json.dumps(probabilities, ensure_ascii=False)
    
    # Initialiser les facteurs de risque par défaut (listes vides)
    risk_factors_json = json.dumps([])
    protective_factors_json = json.dumps([])
    
    # Calculer les SHAP values pour les facteurs de risque (optionnel)
    try:
        ordered_data = {}
        for col in ml_service_instance.feature_names:
            value = normalized_dict.get(col, 0)
            if col in ['Age_diagnostic', 'CD4_debut', 'Score_inf_opp', 'temps_suivi']:
                ordered_data[col] = float(value) if value is not None else 0.0
            else:
                ordered_data[col] = int(bool(value))
        
        df_patient = pd.DataFrame([ordered_data])[ml_service_instance.feature_names]
        
        if hasattr(ml_service_instance.prediction_pipeline, 'named_steps'):
            classifier = ml_service_instance.prediction_pipeline.named_steps.get('classifier')
            preprocessor = ml_service_instance.prediction_pipeline.named_steps.get('preprocessor')
        else:
            classifier = ml_service_instance.prediction_pipeline
            preprocessor = None
        
        if preprocessor is not None:
            try:
                X_processed = preprocessor.transform(df_patient)
            except:
                X_processed = df_patient.values
        else:
            X_processed = df_patient.values
        
        explainer = shap.TreeExplainer(classifier)
        shap_values_all = explainer.shap_values(X_processed)
        
        class_names = ['Décédé', 'Perdu de Vue', 'Transféré', 'Vivant']
        pred_idx = class_names.index(predicted_class)
        
        if isinstance(shap_values_all, list):
            shap_values_raw = shap_values_all[pred_idx][0]
        elif len(shap_values_all.shape) == 3:
            shap_values_raw = shap_values_all[0, :, pred_idx]
        else:
            shap_values_raw = shap_values_all[0]
        
        # Identifier facteurs de risque et protecteurs
        risk_factors_list = []
        protective_factors_list = []
        
        for i, feature in enumerate(ml_service_instance.feature_names):
            if i < len(shap_values_raw):
                shap_val = float(shap_values_raw[i])
                display_name = FEATURE_NAMES_FR.get(feature, feature.replace('_', ' ').title())
                if shap_val > 0.02:
                    risk_factors_list.append(display_name)
                elif shap_val < -0.02:
                    protective_factors_list.append(display_name)
        
        risk_factors_json = json.dumps(risk_factors_list, ensure_ascii=False)
        protective_factors_json = json.dumps(protective_factors_list, ensure_ascii=False)
        
    except Exception as e:
        print(f"⚠️ Erreur calcul SHAP (optionnel): {e}")
        # On garde les listes vides par défaut
    
    # Créer l'enregistrement avec TOUS les champs
    new_pred = PredictionLog(
        age_diagnostic=patient.age_diagnostic,
        cd4_debut=patient.cd4_debut,
        score_inf_opp=float(patient.score_inf_opp),
        temps_suivi=patient.temps_suivi,
        stade_avance=patient.stade_avance,
        non_observant=patient.non_observant,
        hospitalisation=patient.hospitalisation,
        tuberculoses=patient.tuberculoses,
        vit_seul=patient.vit_seul,
        etude_secondaire_ou_plus=patient.etude_secondaire_ou_plus,
        predicted_class=predicted_class,
        confidence=confidence,
        probabilities=probabilities_json,
        risk_factors=risk_factors_json,              # ⭐ OBLIGATOIRE
        protective_factors=protective_factors_json,  # ⭐ OBLIGATOIRE
        clinical_alert=None,
        interpretation=None,
        source="dashboard_crud"
    )
    
    db.add(new_pred)
    db.commit()
    db.refresh(new_pred)
    
    return {
        "success": True,
        "id": new_pred.id,
        "prediction": predicted_class,
        "confidence": confidence
    }

@app.delete("/api/predictions/{prediction_id}")
async def delete_prediction(prediction_id: int, db: Session = Depends(get_db)):
    """Supprime une prédiction"""
    prediction = db.query(PredictionLog).filter(PredictionLog.id == prediction_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prédiction non trouvée")
    
    db.delete(prediction)
    db.commit()
    
    return {"success": True, "message": "Prédiction supprimée"}

# ============================================================================
# 🔐 AUTHENTIFICATION JWT
# ============================================================================

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    from app.auth.two_factor import is_2fa_enabled, verify_2fa_code, verify_temp_2fa_code
    from fastapi import status
    
    print(f"🔍 Tentative de connexion pour: {request.username}")
    
    user = authenticate_user(request.username, request.password)
    if not user:
        print("❌ Mot de passe incorrect")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect"
        )
    
    print(f"✅ Utilisateur authentifié: {request.username}")
    
    # Vérifier si le 2FA est activé
    two_fa_status = is_2fa_enabled(request.username)
    print(f"🔐 2FA activé: {two_fa_status}")
    
    if two_fa_status:
        print(f"📱 Code 2FA reçu: {request.code_2fa}")
        
        if not request.code_2fa:
            print("❌ Code 2FA manquant")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Code 2FA requis"
            )
        
        if not verify_2fa_code(request.username, request.code_2fa) and \
           not verify_temp_2fa_code(request.username, request.code_2fa):
            print("❌ Code 2FA invalide")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Code 2FA invalide"
            )
        print("✅ Code 2FA valide")
    
    access_token = create_access_token(data={"sub": user["username"]})
    print("✅ Token généré avec succès")
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
        full_name=user["full_name"]
    )

@app.get("/api/auth/me", response_model=UserInfo)
async def get_current_user_info(current_user = Depends(get_current_user)):
    """
    Retourne les informations de l'utilisateur connecté
    Nécessite un token JWT valide dans le header Authorization: Bearer <token>
    """
    return UserInfo(
        username=current_user["username"],
        role=current_user["role"],
        email=current_user["email"],
        full_name=current_user["full_name"]
    )


@app.get("/api/auth/protected-example")
async def protected_example(current_user = Depends(require_role(["admin", "doctor"]))):
    """
    Exemple d'endpoint protégé
    Accessible uniquement aux admins et docteurs
    """
    return {
        "message": f"Bienvenue {current_user['full_name']}!",
        "role": current_user["role"],
        "access_granted": True,
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# PAGE D'AUTHENTIFICATION
# ============================================================================

from fastapi.responses import HTMLResponse
from pathlib import Path

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Page d'authentification"""
    login_html_path = Path("app/static/login.html")
    if login_html_path.exists():
        with open(login_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Page d'authentification non trouvée</h1>", status_code=404)

from fastapi import Request
from fastapi.responses import RedirectResponse

def require_auth(request: Request):
    """Middleware pour vérifier l'authentification"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return RedirectResponse(url="/login", status_code=303)
    return None

# ============================================================================
# LOGOUT
# ============================================================================

@app.post("/api/auth/logout")
async def logout():
    """Déconnexion - côté client, il faut supprimer le token"""
    return {"message": "Déconnexion réussie"}

@app.get("/api/test-cookie")
async def test_cookie(request: Request):
    """Teste si le cookie est présent"""
    token = request.cookies.get("access_token")
    return {
        "has_token": token is not None,
        "token_preview": token[:50] if token else None,
        "all_cookies": dict(request.cookies)
    }
@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse("static/favicon.ico")

# ============================================================================
# FIN DU FICHIER
# ============================================================================