#!/usr/bin/env python
"""
🔍 VÉRIFICATION DE LA COHÉRENCE - VIH PREDICTION
Vérifie que main.py, predict.py, ml_service.py, visualizations.py sont cohérents
"""

from app.services.ml_service import MLService
from app.api.predict import PatientInput, PredictionResponse
from app.api.visualizations import PatientInput as VisPatientInput

print("\n" + "="*70)
print("🔍 VÉRIFICATION DE LA COHÉRENCE DES 4 FICHIERS")
print("="*70)

# ========================================================================
# 1. Charger le modèle
# ========================================================================
print("\n1️⃣ CHARGEMENT DU MODÈLE (main.py + ml_service.py)")
print("-" * 70)

ml_service = MLService()
ml_service.load_models()

print(f"✅ Model Type: {type(ml_service.prediction_pipeline).__name__}")
print(f"✅ Features count: {len(ml_service.feature_names)}")
print(f"✅ Feature names: {ml_service.feature_names}")

# ========================================================================
# 2. Vérifier que PatientInput (predict.py) et VisPatientInput 
# (visualizations.py) ont les mêmes champs
# ========================================================================
print("\n2️⃣ VÉRIFICATION DES MODÈLES PYDANTIC")
print("-" * 70)

predict_fields = set(PatientInput.model_fields.keys())
vis_fields = set(VisPatientInput.model_fields.keys())

print(f"Champs predict.py:        {sorted(predict_fields)}")
print(f"Champs visualizations.py: {sorted(vis_fields)}")

if predict_fields == vis_fields:
    print("✅ Les deux modèles Pydantic sont IDENTIQUES")
else:
    print("❌ ERREUR: Les modèles Pydantic sont DIFFÉRENTS")
    print(f"   Différences: {predict_fields ^ vis_fields}")

# ========================================================================
# 3. Tester la conversion snake_case → PascalCase
# ========================================================================
print("\n3️⃣ TEST CONVERSION SNAKE_CASE → PASCALCASE")
print("-" * 70)

patient_dict_snake = {
    'age_diagnostic': 25,
    'cd4_debut': 700,
    'score_inf_opp': 0,
    'temps_suivi': 60,
    'stade_avance': False,
    'non_observant': False,
    'hospitalisation': False,
    'tuberculoses': False,
    'vit_seul': False,
    'etude_secondaire_ou_plus': True
}

print("Input (snake_case):")
for k, v in patient_dict_snake.items():
    model_key = ml_service.input_to_model_mapping.get(k, k)
    print(f"  {k:30} → {model_key:30} = {v}")

pred, probs = ml_service.predict(patient_dict_snake)
conf = max(probs.values())

print(f"\n✅ Prédiction: {pred}")
print(f"✅ Confiance: {conf:.1%}")

# ========================================================================
# 4. Comparer avec les données attendues (Colab)
# ========================================================================
print("\n4️⃣ COMPARAISON AVEC LES RÉSULTATS COLAB")
print("-" * 70)

expected = {
    'prediction': 'Vivant',
    'confidence': 0.669,
    'vivant_proba': 0.669
}

current = {
    'prediction': pred,
    'confidence': conf,
    'vivant_proba': probs.get('Vivant', 0)
}

print(f"Expected: {expected}")
print(f"Current:  {current}")

if (current['prediction'] == expected['prediction'] and 
    abs(current['confidence'] - expected['confidence']) < 0.01):
    print("\n✅ ✅ ✅ COHÉRENCE VALIDÉE ✅ ✅ ✅")
else:
    print("\n❌ ERREUR DE COHÉRENCE")

# ========================================================================
# 5. Afficher les champs du mapping
# ========================================================================
print("\n5️⃣ MAPPING SNAKE_CASE → PASCALCASE (ml_service.py)")
print("-" * 70)
for k, v in ml_service.input_to_model_mapping.items():
    status = "✅" if k != v else "⏸️ "
    print(f"{status} {k:35} → {v}")

print("\n" + "="*70)
print("✅ VÉRIFICATION COMPLÈTE")
print("="*70)
