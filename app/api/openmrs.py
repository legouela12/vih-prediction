"""OpenMRS to HIV prediction workflow.

All model inputs are mapped to OpenMRS concept UUIDs through environment
variables. Missing mappings/observations stop the prediction; no clinical
features are silently fabricated.
"""

import os
import hmac
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

router = APIRouter()

# Stable CIEL UUIDs present in the local OpenMRS dictionary.
CONCEPT_HIV_DIAGNOSIS_DATE = os.getenv(
    "OPENMRS_CONCEPT_HIV_DIAGNOSIS_DATE", "160554AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
CONCEPT_CD4 = os.getenv(
    "OPENMRS_CONCEPT_CD4", "5497AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
OPPORTUNISTIC_INFECTIONS = {
    "Tuberculoses": "112141AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "Cryptococcose": "1219AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "Toxoplasmose": "5355AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "Pneumocystose_pulmonaire": "882AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "Candidose_ophagienne": "146513AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "Parasitose_intestinale": "136677AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
}
CONCEPT_ADMISSION_ENCOUNTER_TYPE = os.getenv(
    "OPENMRS_ENCOUNTER_TYPE_ADMISSION", "e22e39fd-7db2-45e7-80f1-60fa0d5a4378"
)
PREDICTION_FORM_UUID = os.getenv(
    "OPENMRS_PREDICTION_FORM_UUID", "61465e23-9e77-4f68-aa3b-6a6d99773700"
)


def _concept_uuid(env_name: str) -> str:
    value = os.getenv(env_name, "").strip()
    if not value:
        raise HTTPException(
            status_code=503,
            detail=f"Configuration manquante côté serveur: {env_name}",
        )
    return value


async def require_integration_token(
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    configured = os.getenv("OPENMRS_INTEGRATION_TOKEN", "")
    if configured:
        expected = f"Bearer {configured}"
        if authorization and hmac.compare_digest(authorization, expected):
            return

    # The O3 post-submission action calls the API from the browser. Its OpenMRS
    # HttpOnly session cookie is scoped to /openmrs, so this check is exposed
    # under the same path prefix (see the additional router mount in main.py).
    cookie_header = request.headers.get("cookie", "")
    client = getattr(request.app.state, "openmrs_client", None)
    default_origins = "http://127.0.0.1:8080,http://localhost:8080"
    allowed_origins = {
        value.strip()
        for value in os.getenv("OPENMRS_FRONTEND_ORIGINS", default_origins).split(",")
        if value.strip()
    }
    if request.headers.get("origin") not in allowed_origins:
        raise HTTPException(status_code=403, detail="Origine OpenMRS non autorisée")
    if cookie_header and client and client.check_browser_session(cookie_header):
        return

    if not configured:
        raise HTTPException(status_code=503, detail="Jeton d'intégration non configuré")
    raise HTTPException(status_code=401, detail="Authentification requise")


def _raw_value(observation: Optional[Dict[str, Any]]):
    if not observation:
        return None
    return observation.get("value")


def _obs_value(client, patient_uuid: str, concept_uuid: str, order: str = "desc"):
    observations = client.get_observations(
        patient_uuid, concept_uuid, order=order, limit=1
    )
    if observations is None:
        raise HTTPException(status_code=502, detail="Lecture des observations OpenMRS échouée")
    return _raw_value(observations[0]) if observations else None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, dict):
        value = value.get("display") or value.get("value")
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _flag_from_obs(value: Any) -> bool:
    """Notebook binary columns used 0 for absent/missing indicator values."""
    if value is None:
        return False
    if isinstance(value, dict):
        value = value.get("display") or value.get("name") or value.get("uuid")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().casefold()
    return normalized in {
        "yes", "oui", "true", "1", "positive", "positif", "present",
        "présent", "présente", "confirmed", "confirmé", "confirmée",
    }


def _coded_feature(client, patient_uuid: str, env_name: str) -> Any:
    concept_uuid = _concept_uuid(env_name)
    return _obs_value(client, patient_uuid, concept_uuid)


def _build_features(client, patient_uuid: str, patient: Dict[str, Any]) -> Dict[str, Any]:
    person = patient.get("person") or {}
    diagnosis_value = _obs_value(
        client, patient_uuid, CONCEPT_HIV_DIAGNOSIS_DATE, order="desc"
    )
    diagnosis_date = _as_date(diagnosis_value)
    birth_date = _as_date(person.get("birthdate"))

    missing = []
    if not diagnosis_date:
        missing.append("Date_de_decouverte_de_seropositivite")
    if not birth_date:
        missing.append("Date_de_naissance")

    initial_cd4_value = _obs_value(
        client, patient_uuid, CONCEPT_CD4, order="asc"
    )
    try:
        initial_cd4 = float(initial_cd4_value)
        if initial_cd4 < 0:
            raise ValueError
    except (TypeError, ValueError):
        initial_cd4 = None
        missing.append("Taux_de_CD4_au_debut_de_traitement")

    encounters = client.get_encounters(patient_uuid)
    if encounters is None:
        raise HTTPException(status_code=502, detail="Lecture des rencontres OpenMRS échouée")
    last_contact = None
    for encounter in encounters:
        encounter_date = _as_date(encounter.get("encounterDatetime"))
        if encounter_date and (last_contact is None or encounter_date > last_contact):
            last_contact = encounter_date

    death_date = _as_date(person.get("deathDate")) if person.get("dead") else None
    followup_end = death_date or last_contact
    if not followup_end:
        missing.append("Date_de_derniere_visite")

    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Données requises absentes pour calculer les variables du modèle.",
                "fields": missing,
            },
        )

    age_at_diagnosis = round((diagnosis_date - birth_date).days / 365.25, 1)
    # Le notebook d'entraînement exprime `temps_suivi` en mois depuis le
    # diagnostic VIH : jours écoulés / 30,44, avec un minimum de 0,1 mois.
    followup_months = max((followup_end - diagnosis_date).days / 30.44, 0.1)

    diagnosis_uuids = client.get_patient_diagnosis_uuids(patient_uuid)
    if diagnosis_uuids is None:
        raise HTTPException(status_code=502, detail="Lecture des diagnostics OpenMRS échouée")

    opportunistic_score = 0
    tuberculosis = False
    for feature, concept_uuid in OPPORTUNISTIC_INFECTIONS.items():
        value = _obs_value(client, patient_uuid, concept_uuid)
        present = concept_uuid in diagnosis_uuids or _flag_from_obs(value)
        if feature == "Tuberculoses":
            tuberculosis = present
        opportunistic_score += int(present)

    stade_avance = _flag_from_obs(
        _coded_feature(client, patient_uuid, "OPENMRS_CONCEPT_STADE_AVANCE")
    )
    non_observant = _flag_from_obs(
        _coded_feature(client, patient_uuid, "OPENMRS_CONCEPT_NON_OBSERVANT")
    )
    lives_alone = _flag_from_obs(
        _coded_feature(client, patient_uuid, "OPENMRS_CONCEPT_VIT_SEUL")
    )
    secondary_plus = _flag_from_obs(
        _coded_feature(client, patient_uuid, "OPENMRS_CONCEPT_ETUDE_SECONDAIRE_PLUS")
    )

    hospitalized = client.has_encounter_type(
        patient_uuid, CONCEPT_ADMISSION_ENCOUNTER_TYPE
    )
    if hospitalized is None:
        raise HTTPException(status_code=502, detail="Lecture des hospitalisations OpenMRS échouée")

    return {
        "age_diagnostic": age_at_diagnosis,
        "cd4_debut": initial_cd4,
        "score_inf_opp": opportunistic_score,
        "temps_suivi": followup_months,
        "stade_avance": stade_avance,
        "non_observant": non_observant,
        "hospitalisation": hospitalized,
        "tuberculoses": tuberculosis,
        "vit_seul": lives_alone,
        "etude_secondaire_ou_plus": secondary_plus,
    }


@router.get("/openmrs/health")
async def openmrs_health(request: Request):
    result = request.app.state.openmrs_client.check_connection()
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=200 if result.get("authenticated") else 503,
        content={"service": "openmrs", **result},
    )


async def _run_patient_prediction(
    patient_uuid: str,
    request: Request,
    *,
    save_to_openmrs: bool,
    encounter_uuid: Optional[str] = None,
) -> Dict[str, Any]:
    client = request.app.state.openmrs_client
    ml_service = getattr(request.app.state, "ml_service", None)
    if ml_service is None or ml_service.prediction_pipeline is None:
        raise HTTPException(status_code=503, detail="Modèle de prédiction non initialisé")

    patient = client.get_patient(patient_uuid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient introuvable dans OpenMRS")

    features = _build_features(client, patient_uuid, patient)

    predicted_class, probabilities = ml_service.predict(features)
    confidence = max(probabilities.values())
    model_info = ml_service.get_model_info()
    generated_at = datetime.now(timezone.utc)
    result = {
        "patient_uuid": patient_uuid,
        "prediction": predicted_class,
        "confidence": confidence,
        "probabilities": probabilities,
        "model_version": model_info.get("version", "unknown"),
        "generated_at": generated_at.isoformat(),
        "features_used": features,
        "interpretation": (
            "Aide à la décision issue d'un modèle; ne constitue pas un diagnostic. "
            "À interpréter et valider par un professionnel de santé."
        ),
    }

    if not save_to_openmrs:
        result["saved_to_openmrs"] = False
        return result

    output_concept = _concept_uuid("OPENMRS_CONCEPT_PREDICTION_RESULT")
    observation_text = (
        f"Prédiction IA (aide à la décision): {predicted_class}; "
        f"confiance {confidence:.3f}; modèle {result['model_version']}; "
        f"date {result['generated_at']}. À valider par un professionnel."
    )
    if encounter_uuid:
        target_encounter = client.get_encounter(encounter_uuid)
        if not target_encounter:
            raise HTTPException(status_code=404, detail="Rencontre OpenMRS introuvable")
        encounter_patient_uuid = (target_encounter.get("patient") or {}).get("uuid")
        form_uuid = (target_encounter.get("form") or {}).get("uuid")
        if encounter_patient_uuid != patient_uuid:
            raise HTTPException(status_code=422, detail="La rencontre ne correspond pas au patient")
        expected_form_uuid = os.getenv("OPENMRS_PREDICTION_FORM_UUID", PREDICTION_FORM_UUID).strip()
        if form_uuid != expected_form_uuid:
            raise HTTPException(status_code=422, detail="Cette rencontre ne vient pas du formulaire VIH configuré")
        output_concept_uuid = _concept_uuid("OPENMRS_CONCEPT_PREDICTION_RESULT")
        already_has_result = any(
            (obs.get("concept") or {}).get("uuid") == output_concept_uuid
            and not obs.get("voided", False)
            for obs in (target_encounter.get("obs") or [])
        )
        if already_has_result:
            raise HTTPException(status_code=409, detail="Cette rencontre possède déjà un résultat de prédiction")
    else:
        encounters = client.get_encounters(patient_uuid)
        if encounters is None:
            raise HTTPException(status_code=502, detail="Lecture des rencontres OpenMRS échouée")
        encounters.sort(key=lambda item: item.get("encounterDatetime") or "", reverse=True)
        target_encounter = encounters[0] if encounters else None
        if not target_encounter:
            raise HTTPException(
                status_code=422,
                detail="Aucune rencontre OpenMRS pour rattacher le résultat au dossier patient.",
            )
        encounter_uuid = target_encounter.get("uuid")

    location_uuid = (target_encounter.get("location") or {}).get("uuid")
    if not encounter_uuid or not location_uuid:
        raise HTTPException(
            status_code=422,
            detail="La dernière rencontre OpenMRS ne contient pas d’UUID de rencontre ou de lieu.",
        )
    try:
        obs = client.create_observation(
            patient_uuid=patient_uuid,
            concept_uuid=output_concept,
            value=observation_text,
            encounter_uuid=encounter_uuid,
            location_uuid=location_uuid,
            obs_datetime=(
                generated_at.strftime("%Y-%m-%dT%H:%M:%S.")
                + f"{generated_at.microsecond // 1000:03d}+0000"
            ),
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        openmrs_reason = ""
        if response is not None:
            openmrs_reason = (
                f" HTTP {response.status_code}: {response.text[:400]}"
            )
        raise HTTPException(
            status_code=502,
            detail=(
                "Prédiction calculée, mais enregistrement OpenMRS échoué "
                f"({type(exc).__name__}).{openmrs_reason}"
            ),
        ) from exc

    result["openmrs_observation_uuid"] = obs.get("uuid") if isinstance(obs, dict) else None
    result["saved_to_openmrs"] = True
    return result


@router.post("/openmrs/patient/{patient_uuid}/predict")
async def predict_and_save_from_openmrs(
    patient_uuid: str,
    request: Request,
    _auth=Depends(require_integration_token),
):
    """Read mapped features, predict, and save an informational OpenMRS obs."""
    return await _run_patient_prediction(patient_uuid, request, save_to_openmrs=True)


@router.post("/openmrs/encounter/{encounter_uuid}/predict")
async def predict_from_submitted_form(
    encounter_uuid: str,
    request: Request,
    _auth=Depends(require_integration_token),
):
    """Predict for a just-submitted evaluation form and link output to that encounter."""
    client = request.app.state.openmrs_client
    encounter = client.get_encounter(encounter_uuid)
    if not encounter:
        raise HTTPException(status_code=404, detail="Rencontre OpenMRS introuvable")
    patient_uuid = (encounter.get("patient") or {}).get("uuid")
    if not patient_uuid:
        raise HTTPException(status_code=422, detail="Patient absent de la rencontre OpenMRS")
    return await _run_patient_prediction(
        patient_uuid,
        request,
        save_to_openmrs=True,
        encounter_uuid=encounter_uuid,
    )


@router.get("/predict-from-openmrs/{patient_uuid}")
async def predict_from_openmrs_compat(
    patient_uuid: str,
    request: Request,
    _auth=Depends(require_integration_token),
):
    """Legacy read-only route; use the POST route to save an observation."""
    return await _run_patient_prediction(patient_uuid, request, save_to_openmrs=False)
