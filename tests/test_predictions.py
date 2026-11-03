"""
Tests pour les endpoints de prédiction
"""
import pytest
from fastapi import status


class TestShapExplainEndpoint:
    """Tests pour l'endpoint /api/viz/shap-explain"""
    
    def test_shap_explain_success(self, client, sample_patient):
        """Test une prédiction SHAP réussie"""
        response = client.post("/api/viz/shap-explain", json=sample_patient)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Vérifier la structure de la réponse
        expected_fields = ["prediction", "confidence", "probabilities", "shap_values", 
                          "risk_factors", "protective_factors", "interpretation"]
        for field in expected_fields:
            assert field in data

        expected_outcomes = ["Décédé", "Perdu de Vue", "Transféré", "Vivant"]
        assert all(outcome in data["probabilities"] for outcome in expected_outcomes)
        assert all(0 <= data["probabilities"][outcome] <= 1 for outcome in expected_outcomes)
        
        # Vérifier que la prédiction est valide
        assert data["prediction"] in ["Décédé", "Perdu de Vue", "Transféré", "Vivant"]
        
        # Vérifier que la confiance est entre 0 et 1
        assert 0 <= data["confidence"] <= 1
    
    def test_shap_explain_high_risk(self, client, high_risk_patient):
        """Test prédiction pour patient à haut risque"""
        response = client.post("/api/viz/shap-explain", json=high_risk_patient)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Un patient à haut risque devrait être prédit comme Décédé
        # Note: selon les règles cliniques, peut être ajusté
        assert data["prediction"] in ["Décédé", "Perdu de Vue"]
    
    def test_shap_explain_good_prognosis(self, client, good_prognosis_patient):
        """Test prédiction pour patient à bon pronostic"""
        response = client.post("/api/viz/shap-explain", json=good_prognosis_patient)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Un patient à bon pronostic devrait être prédit comme Vivant
        assert data["prediction"] in ["Vivant", "Transféré"]
    
    def test_shap_explain_validation_error(self, client):
        """Test erreur de validation avec données invalides"""
        invalid_patient = {
            "age_diagnostic": -5,  # Âge négatif invalide
            "cd4_debut": 450,
            "score_inf_opp": 0,
            "temps_suivi": 24
        }
        response = client.post("/api/viz/shap-explain", json=invalid_patient)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_shap_explain_missing_fields(self, client):
        """Test erreur avec champs manquants"""
        incomplete_patient = {
            "age_diagnostic": 35,
            "cd4_debut": 450
        }
        response = client.post("/api/viz/shap-explain", json=incomplete_patient)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_shap_values_format(self, client, sample_patient):
        """Test le format des valeurs SHAP"""
        response = client.post("/api/viz/shap-explain", json=sample_patient)
        data = response.json()
        
        shap_values = data["shap_values"]
        expected_features = ["Âge au diagnostic", "CD4 initial", "Score infections opportunistes",
                            "Durée de suivi", "Stade avancé", "Non-observance",
                            "Hospitalisation", "Tuberculose", "Vit seul", "Étude secondaire+"]
        
        # Vérifier que toutes les features sont présentes
        for feature in expected_features:
            assert feature in shap_values


class TestPredictionUI:
    """Tests pour l'interface utilisateur /api/predict-ui"""
    
    def test_predict_ui_accessible(self, client):
        """Test que l'interface utilisateur est accessible"""
        response = client.get("/api/predict-ui")
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
    
    def test_predict_ui_contains_form(self, client):
        """Test que l'interface contient le formulaire"""
        response = client.get("/api/predict-ui")
        content = response.text
        assert "form" in content.lower()
        assert "age_diagnostic" in content
        assert "cd4_debut" in content
        assert 'id="date_naissance"' in content
        assert 'id="date_seropositivite"' in content
        assert 'id="date_derniere_observation"' in content
        assert "365.25" in content
        assert "30.44" in content
        assert "data.probabilities[name]" in content
        for outcome in ["Décédé", "Perdu de Vue", "Transféré", "Vivant"]:
            assert outcome in content


class TestDashboardCRUD:
    """Tests pour le dashboard CRUD"""
    
    def test_dashboard_crud_accessible(self, client):
        """Test que le dashboard CRUD est accessible"""
        response = client.get("/api/dashboard-crud")
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
    
    def test_dashboard_crud_contains_table(self, client):
        """Test que le dashboard contient un tableau"""
        response = client.get("/api/dashboard-crud")
        content = response.text
        assert "predictionsTable" in content or "table" in content.lower()