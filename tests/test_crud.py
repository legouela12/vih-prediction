"""
Tests pour les endpoints CRUD
"""
import pytest
from fastapi import status


class TestGetPredictions:
    """Tests pour GET /api/predictions"""
    
    def test_get_predictions_empty(self, client):
        """Test récupération des prédictions (vide au début)"""
        response = client.get("/api/predictions")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] == True
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
    
    def test_get_predictions_with_pagination(self, client):
        """Test pagination des prédictions"""
        response = client.get("/api/predictions?page=1&limit=10")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["page"] == 1
        assert data["limit"] in [10, 20]  # Limite par défaut
    
    def test_get_predictions_filter_by_class(self, client):
        """Test filtrage par classe"""
        response = client.get("/api/predictions?prediction_class=Vivant")
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_predictions_stats(self, client):
        """Test récupération des statistiques"""
        response = client.get("/api/predictions/stats")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "by_class" in data
        assert "trend" in data


class TestCreatePrediction:
    """Tests pour POST /api/predictions"""
    
    def test_create_prediction_success(self, client, sample_patient):
        """Test création réussie d'une prédiction"""
        response = client.post("/api/predictions", json=sample_patient)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] == True
        assert "id" in data
        assert "prediction" in data
        assert "confidence" in data
        
        # Vérifier que l'ID est un entier positif
        assert isinstance(data["id"], int)
        assert data["id"] > 0
    
    def test_create_prediction_high_risk(self, client, high_risk_patient):
        """Test création prédiction patient haut risque"""
        response = client.post("/api/predictions", json=high_risk_patient)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] == True
        assert data["prediction"] in ["Décédé", "Perdu de Vue", "Transféré", "Vivant"]
    
    def test_create_prediction_invalid_age(self, client):
        """Test création avec âge invalide"""
        invalid_patient = {
            "age_diagnostic": -10,
            "cd4_debut": 450,
            "score_inf_opp": 0,
            "temps_suivi": 24,
            "stade_avance": False,
            "non_observant": False,
            "hospitalisation": False,
            "tuberculoses": False,
            "vit_seul": False,
            "etude_secondaire_ou_plus": True
        }
        response = client.post("/api/predictions", json=invalid_patient)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_prediction_invalid_cd4(self, client):
        """Test création avec CD4 invalide"""
        invalid_patient = {
            "age_diagnostic": 35,
            "cd4_debut": -100,
            "score_inf_opp": 0,
            "temps_suivi": 24
        }
        response = client.post("/api/predictions", json=invalid_patient)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestDeletePrediction:
    """Tests pour DELETE /api/predictions/{id}"""
    
    def test_delete_nonexistent_prediction(self, client):
        """Test suppression d'une prédiction inexistante"""
        response = client.delete("/api/predictions/99999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_delete_prediction_success(self, client, sample_patient):
        """Test suppression réussie d'une prédiction"""
        # D'abord créer une prédiction
        create_response = client.post("/api/predictions", json=sample_patient)
        prediction_id = create_response.json()["id"]
        
        # Puis la supprimer
        delete_response = client.delete(f"/api/predictions/{prediction_id}")
        assert delete_response.status_code == status.HTTP_200_OK
        data = delete_response.json()
        assert data["success"] == True
        assert "message" in data


class TestGetPredictionDetail:
    """Tests pour GET /api/predictions/{id}"""
    
    def test_get_nonexistent_prediction(self, client):
        """Test récupération d'une prédiction inexistante"""
        response = client.get("/api/predictions/99999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_prediction_detail_success(self, client, sample_patient):
        """Test récupération des détails d'une prédiction"""
        # Créer une prédiction
        create_response = client.post("/api/predictions", json=sample_patient)
        prediction_id = create_response.json()["id"]
        
        # Récupérer les détails
        response = client.get(f"/api/predictions/{prediction_id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] == True
        assert "data" in data
        assert data["data"]["id"] == prediction_id