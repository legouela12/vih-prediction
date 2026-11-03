from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db, test_connection
from app.database.crud import get_dashboard_stats

router = APIRouter()


@router.get('/viz/dashboard')
async def dashboard_stats(db: Session = Depends(get_db)):
    stats = get_dashboard_stats(db)
    return {
        'success': True,
        'dashboard': stats,
        'meta': {
            'source': 'backend',
            'description': 'Statistiques de prédictions VIH enregistrées en base'
        }
    }


@router.get('/viz/health')
async def viz_health():
    db_ok, db_error = test_connection()
    return {
        'success': db_ok,
        'status': 'healthy' if db_ok else 'unhealthy',
        'database_connected': db_ok,
        'database_error': db_error,
        'message': 'Vérification de la connexion à la base de données MySQL',
    }
