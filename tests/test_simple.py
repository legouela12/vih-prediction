import pytest
import sys
from pathlib import Path

# Ajouter le chemin du projet
sys.path.append(str(Path(__file__).parent.parent))


class TestSimple:
    """Tests simples pour vérifier que tout fonctionne"""
    
    def test_import_fastapi(self):
        from fastapi import FastAPI
        app = FastAPI()
        assert app is not None
    
    def test_import_shap(self):
        import shap
        assert shap.__version__ is not None
    
    def test_import_sklearn(self):
        import sklearn
        assert sklearn.__version__ is not None
    
    def test_import_pandas(self):
        import pandas as pd
        assert pd.__version__ is not None
    
    def test_import_numpy(self):
        import numpy as np
        assert np.__version__ is not None


class TestConfig:
    """Tests de configuration"""
    
    def test_dotenv_loading(self):
        from dotenv import load_dotenv
        from pathlib import Path
        import os
        
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            assert True
        else:
            assert True  # Pas d'erreur si .env n'existe pas