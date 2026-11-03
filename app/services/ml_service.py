import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple, List
from sklearn.pipeline import Pipeline
from dotenv import load_dotenv

load_dotenv()

class MLService:
    def __init__(self):
        self.prediction_pipeline = None
        self.classes_ = None
        self.feature_names = [
            'Age_diagnostic', 'CD4_debut', 'Score_inf_opp', 'temps_suivi',
            'Stade_avance', 'Non_observant', 'Hospitalisation', 
            'Tuberculoses', 'Vit_seul', 'Etude_secondaire_ou_plus'
        ]
        
        # Mapping des classes
        self.class_mapping = {
            0: 'Décédé',
            1: 'Perdu de Vue',
            2: 'Transféré',
            3: 'Vivant'
        }
        
        # ✅ Mapping snake_case → PascalCase pour la conversion des inputs
        self.input_to_model_mapping = {
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
        
    def load_models(self):
        """Charge et prépare le pipeline pour la prédiction"""
        base_path = Path(__file__).parent.parent.parent
        possible_paths = [
            base_path / "models" / "best_model_final.joblib",
            base_path / "best_model_final.joblib",
            Path("models/best_model_final.joblib"),
            Path("best_model_final.joblib")
        ]
        
        model_path = None
        for path in possible_paths:
            if path.exists():
                model_path = path
                break
        
        if model_path is None:
            raise FileNotFoundError(f"Modèle non trouvé")
        
        print(f"📂 Chargement: {model_path}")
        full_pipeline = joblib.load(model_path)
        
        # Retirer SMOTE si présent
        if hasattr(full_pipeline, 'named_steps'):
            steps_without_smote = [(name, step) for name, step in full_pipeline.steps if name != 'smote']
            self.prediction_pipeline = Pipeline(steps_without_smote)
        else:
            self.prediction_pipeline = full_pipeline
        
        print("✅ Modèle chargé")
        return True
    
    def predict(self, features: Dict[str, Any]) -> Tuple[str, Dict[str, float]]:
        """Prédiction pour un nouveau patient"""
        
        # ✅ Convertir les clés snake_case en PascalCase si nécessaire
        normalized_features = {}
        for key, value in features.items():
            # Si la clé est en snake_case, convertir; sinon, garder comme-est
            model_key = self.input_to_model_mapping.get(key, key)
            normalized_features[model_key] = value
        
        # Préparer les données
        data = {}
        for col in self.feature_names:
            value = normalized_features.get(col, 0)
            if col in ['Age_diagnostic', 'CD4_debut', 'Score_inf_opp', 'temps_suivi']:
                data[col] = float(value) if value is not None else 0.0
            else:
                data[col] = 1 if value else 0
        
        # DataFrame
        df = pd.DataFrame([data])[self.feature_names]
        
        # Prédiction
        proba = self.prediction_pipeline.predict_proba(df)[0]
        pred_idx = np.argmax(proba)
        
        # Résultat
        predicted_class = self.class_mapping.get(pred_idx, f"Classe_{pred_idx}")
        probabilities = {self.class_mapping.get(i, f"Classe_{i}"): float(p) for i, p in enumerate(proba)}
        
        return predicted_class, probabilities
    
    def predict_batch(self, patients: List[Dict]) -> List[Dict]:
        """Prédiction batch"""
        results = []
        for i, patient in enumerate(patients):
            try:
                pred_class, probs = self.predict(patient)
                results.append({
                    "patient_index": i,
                    "prediction": pred_class,
                    "confidence": max(probs.values()),
                    "probabilities": probs
                })
            except Exception as e:
                results.append({
                    "patient_index": i,
                    "error": str(e)
                })
        return results
    
    def get_model_info(self) -> Dict:
        """Informations du modèle"""
        return {
            "model_name": "Random Forest Optimisé",
            "model_type": type(self.prediction_pipeline).__name__ if self.prediction_pipeline else "Unknown",
            "classes": list(self.class_mapping.values()),
            "features": self.feature_names,
            "n_features": len(self.feature_names),
            "version": "1.0.0"
        }