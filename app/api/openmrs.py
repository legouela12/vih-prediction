from fastapi import APIRouter, HTTPException, Request
from typing import Optional

router = APIRouter()

# UUID des concepts OpenMRS (vérifiés sur votre instance locale)
CONCEPT_CD4 = "be53d1d4-1691-11df-97a5-7038c432aabf"
CONCEPT_VIRAL_LOAD = "be48600d-1691-11df-97a5-7038c432aabf"

# Valeurs par défaut pour les features manquantes (à adapter selon votre modèle)
DEFAULT_FEATURES = {
    "Score_inf_opp": 0.0,
    "temps_suivi": 12.0,      # 12 mois par défaut
    "Stade_avance": 0,
    "Non_observant": 0,
    "Hospitalisation": 0,
    "Tuberculoses": 0,
    "Vit_seul": 0,
    "Etude_secondaire_ou_plus": 0,
}

@router.get("/openmrs/health")
async def openmrs_health(request: Request):
    """Vérifie la disponibilité et l'authentification auprès d'OpenMRS."""
    openmrs_client = request.app.state.openmrs_client
    result = openmrs_client.check_connection()
    status_code = 200 if result.get("authenticated") else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={
        "service": "openmrs",
        "base_url": openmrs_client.base_url,
        **result,
    })

@router.get("/predict-from-openmrs/{patient_uuid}")
async def predict_from_openmrs(patient_uuid: str, request: Request):
    """
    Endpoint GET qui interroge OpenMRS pour récupérer le CD4 et la charge virale,
    puis retourne la prédiction du modèle.
    """
    # Récupère le client OpenMRS depuis l'état de l'application
    openmrs_client = request.app.state.openmrs_client

    # 1. Récupérer les infos patient (âge)
    patient_data = openmrs_client.get_patient(patient_uuid)
    if not patient_data:
        raise HTTPException(status_code=404, detail="Patient non trouvé dans OpenMRS")

    # 2. Récupérer les observations cliniques
    cd4 = openmrs_client.get_latest_obs_value(patient_uuid, CONCEPT_CD4)
    viral_load = openmrs_client.get_latest_obs_value(patient_uuid, CONCEPT_VIRAL_LOAD)
    # Si les observations sont manquantes, on nève pas une 404 —
    # on utilise des valeurs par défaut et on renvoie un avertissement
    missing = []
    if cd4 is None:
        missing.append('CD4')
        cd4 = 0.0
    if viral_load is None:
        missing.append('Charge Virale')
        viral_load = 0.0

    if missing:
        print(f"⚠️ Données cliniques manquantes pour {patient_uuid}: {', '.join(missing)}. Valeurs par défaut utilisées.")
        warning = f"Données cliniques manquantes : {', '.join(missing)} — valeurs par défaut utilisées."
    else:
        warning = None

    print(f"✅ Données récupérées pour {patient_uuid}: CD4={cd4}, VL={viral_load}")

    # 3. Extraire l'âge
    person = patient_data.get('person', {})
    age = person.get('age', 40)

    # 4. Assembler les 10 features pour le modèle
    features = {
        'Age_diagnostic': age,
        'CD4_debut': cd4,
        'Score_inf_opp': DEFAULT_FEATURES['Score_inf_opp'],
        'temps_suivi': DEFAULT_FEATURES['temps_suivi'],
        'Stade_avance': DEFAULT_FEATURES['Stade_avance'],
        'Non_observant': DEFAULT_FEATURES['Non_observant'],
        'Hospitalisation': DEFAULT_FEATURES['Hospitalisation'],
        'Tuberculoses': DEFAULT_FEATURES['Tuberculoses'],
        'Vit_seul': DEFAULT_FEATURES['Vit_seul'],
        'Etude_secondaire_ou_plus': DEFAULT_FEATURES['Etude_secondaire_ou_plus'],
    }

    # 5. Appeler le service ML
    if not hasattr(request.app.state, "ml_service") or request.app.state.ml_service is None:
        raise HTTPException(status_code=503, detail="Service ML non initialisé")

    ml_service = request.app.state.ml_service
    predicted_class, probabilities = ml_service.predict(features)
    confidence = max(probabilities.values())

    # 6. Retourner la réponse
    return {
        "success": True,
        "patient_uuid": patient_uuid,
        "cd4": cd4,
        "viral_load": viral_load,
        "prediction": predicted_class,
        "confidence": confidence,
        "probabilities": probabilities,
        "features_used": features,
        "warning": warning
    }