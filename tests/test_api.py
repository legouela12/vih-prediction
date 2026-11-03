"""
Tests pour les endpoints généraux de l'API
"""
import pytest
from fastapi import status


class TestHealthEndpoint:
    """Tests pour l'endpoint /health"""
    
    def test_health_check(self, client):
        """Test que l'endpoint health retourne un statut healthy"""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["model"]["loaded"] == True
        assert data["components"]["static_dir"] == True
    
    def test_health_response_structure(self, client):
        """Test la structure de la réponse health"""
        response = client.get("/health")
        data = response.json()
        
        required_fields = ["status", "timestamp", "model", "components"]
        for field in required_fields:
            assert field in data
        
        model_fields = ["loaded", "pipeline_ready", "classes_ready", "classes"]
        for field in model_fields:
            assert field in data["model"]


class TestRootEndpoint:
    """Tests pour l'endpoint racine /"""
    
    def test_root_endpoint(self, client):
        """Test que l'endpoint racine retourne les infos API"""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "message" in data
        assert "version" in data
        assert "endpoints" in data
        assert "clinical_warning" in data
    
    def test_root_contains_endpoints(self, client):
        """Test que la racine liste tous les endpoints"""
        response = client.get("/")
        data = response.json()
        
        endpoints = data.get("endpoints", {})
        assert "prediction" in endpoints
        assert "visualizations" in endpoints
        assert "documentation" in endpoints


class TestPingEndpoint:
    """Tests pour l'endpoint /ping"""
    
    def test_ping(self, client):
        """Test que le ping retourne pong"""
        response = client.get("/ping")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["pong"] == True
        assert "timestamp" in data


class TestStaticEndpoints:
    """Tests pour les endpoints statiques"""
    
    def test_test_static(self, client):
        """Test l'endpoint /test-static"""
        response = client.get("/test-static")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "static_dir_exists" in data
        assert "plots_dir_exists" in data
        assert data["static_dir_exists"] == True