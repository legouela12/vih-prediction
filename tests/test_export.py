"""
Tests pour les endpoints d'export
"""
import pytest
import csv
import json
from fastapi import status
from io import StringIO


class TestExportPredictions:
    """Tests pour GET /api/export/predictions"""
    
    def test_export_csv_default(self, client):
        """Test export CSV par défaut"""
        response = client.get("/api/export/predictions")
        assert response.status_code == status.HTTP_200_OK
        assert "text/csv" in response.headers["content-type"]
        assert "attachment; filename=" in response.headers["content-disposition"]
        
        # Vérifier que le contenu est du CSV valide
        content = response.content.decode('utf-8')
        assert "ID,Date,Âge,CD4" in content or "ID" in content
    
    def test_export_json_format(self, client):
        """Test export au format JSON"""
        response = client.get("/api/export/predictions?format=json")
        assert response.status_code == status.HTTP_200_OK
        assert "application/json" in response.headers["content-type"]
        
        # Vérifier que le contenu est du JSON valide
        data = response.json()
        assert isinstance(data, list)
    
    def test_export_with_limit(self, client):
        """Test export avec limite"""
        response = client.get("/api/export/predictions?limit=5")
        assert response.status_code == status.HTTP_200_OK
        
        # Compter les lignes (en ignorant l'en-tête pour CSV)
        content = response.content.decode('utf-8')
        lines = content.strip().split('\n')
        # CSV a une ligne d'en-tête + les données
        assert len(lines) <= 6  # 5 données + 1 en-tête
    
    def test_export_filter_by_class(self, client):
        """Test export avec filtre par classe"""
        response = client.get("/api/export/predictions?prediction_class=Vivant")
        assert response.status_code == status.HTTP_200_OK
    
    def test_export_filter_by_date(self, client):
        """Test export avec filtre par date"""
        response = client.get("/api/export/predictions?start_date=2026-06-01&end_date=2026-06-30")
        assert response.status_code == status.HTTP_200_OK
    
    def test_export_csv_encoding(self, client):
        """Test que l'export CSV utilise l'encodage UTF-8 avec BOM"""
        response = client.get("/api/export/predictions?format=csv")
        content = response.content
        
        # Vérifier la présence du BOM UTF-8
        assert content.startswith(b'\xef\xbb\xbf')  # UTF-8 BOM
    
    def test_export_invalid_format(self, client):
        """Test avec format invalide (devrait utiliser CSV par défaut)"""
        response = client.get("/api/export/predictions?format=xml")
        assert response.status_code == status.HTTP_200_OK
        assert "text/csv" in response.headers["content-type"]


class TestExportContent:
    """Tests pour le contenu de l'export"""
    
    def test_export_contains_required_columns(self, client):
        """Test que l'export CSV contient toutes les colonnes requises"""
        response = client.get("/api/export/predictions?limit=1")
        content = response.content.decode('utf-8')
        
        required_columns = ["ID", "Date", "Âge", "CD4", "Prédiction", "Confiance"]
        for col in required_columns:
            assert col in content
    
    def test_json_export_structure(self, client):
        """Test la structure du JSON exporté"""
        response = client.get("/api/export/predictions?format=json&limit=1")
        data = response.json()
        
        if len(data) > 0:
            first_record = data[0]
            expected_fields = ["id", "created_at", "age_diagnostic", "cd4_debut", 
                              "predicted_class", "confidence"]
            for field in expected_fields:
                assert field in first_record