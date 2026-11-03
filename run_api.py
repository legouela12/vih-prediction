#!/usr/bin/env python
"""
🚀 LANCER L'API VIH PREDICTION

Exécution:
    python run_api.py

L'API sera disponible sur:
    - http://localhost:8000
    - API Docs: http://localhost:8000/docs
    - ReDoc: http://localhost:8000/redoc
"""

import uvicorn
import sys
from pathlib import Path

# Ajouter le dossier racine au path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 DÉMARRAGE DE L'API VIH PREDICTION")
    print("="*70)
    print("📍 URL: http://localhost:8000")
    print("📚 Docs: http://localhost:8000/docs")
    print("📚 ReDoc: http://localhost:8000/redoc")
    print("="*70 + "\n")
    
    # Lancer Uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
