#!/usr/bin/env python
from app.services.ml_service import MLService

ml_service = MLService()
ml_service.load_models()

patient_snake = {
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

print("="*60)
print("✅ TEST CONVERSION SNAKE_CASE → PASCALCASE")
print("="*60)

pred, probs = ml_service.predict(patient_snake)
conf = max(probs.values())

print(f"Prédiction: {pred}")
print(f"Confiance: {conf:.1%}")
print(f"Vivant: {probs.get('Vivant', 0):.1%}")
print(f"\nTous les probs:")
for k, v in probs.items():
    print(f"  {k}: {v:.1%}")
    
print(f"\n✅ RÉSULTAT ATTENDU: Vivant 66.9%")
