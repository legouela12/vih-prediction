from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from jose import jwt
import os
from app.database.connection import get_db  
from dotenv import load_dotenv
from app.database.crud import create_prediction_log

load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ma_super_cle_secrete_pour_jwt_2024_change_me")
ALGORITHM = "HS256"

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
import shap
import hashlib
import time
from pathlib import Path
import os

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static" / "plots"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

print(f"📁 Dossier SHAP plots: {STATIC_DIR.absolute()}")
print(f"📁 Existe: {STATIC_DIR.exists()}")
print(f"📁 Accessible en écriture: {os.access(STATIC_DIR, os.W_OK)}")

MIN_CONFIDENCE_THRESHOLD = 0.50
LOW_CONFIDENCE_THRESHOLD = 0.30

FEATURE_NAMES_FR = {
    'temps_suivi': 'Durée de suivi',
    'Age_diagnostic': 'Âge au diagnostic',
    'CD4_debut': 'CD4 initial',
    'Score_inf_opp': 'Score infections opportunistes',
    'Stade_avance': 'Stade avancé',
    'Non_observant': 'Non-observance',
    'Hospitalisation': 'Hospitalisation',
    'Tuberculoses': 'Tuberculose',
    'Vit_seul': 'Vit seul',
    'Etude_secondaire_ou_plus': 'Étude secondaire+'
}
FEATURE_NAMES_EN = {v: k for k, v in FEATURE_NAMES_FR.items()}

def get_confidence_alert(confidence: float, predicted_class: str) -> dict:
    if confidence >= MIN_CONFIDENCE_THRESHOLD:
        return {
            'level': 'good',
            'message': f"✅ Confiance suffisante ({confidence:.1%}) - La prédiction est fiable",
            'color': '#27ae60',
            'icon': '✅'
        }
    elif confidence >= LOW_CONFIDENCE_THRESHOLD:
        return {
            'level': 'medium',
            'message': f"⚠️ Confiance modérée ({confidence:.1%}) - Interpréter avec prudence. Une évaluation clinique complémentaire est recommandée.",
            'color': '#f39c12',
            'icon': '⚠️'
        }
    else:
        return {
            'level': 'low',
            'message': f"🔴 Confiance TRÈS FAIBLE ({confidence:.1%}) - La prédiction n'est PAS fiable. Une évaluation clinique approfondie est OBLIGATOIRE.",
            'color': '#e74c3c',
            'icon': '🔴'
        }

ml_service_instance = None
def get_ml_service():
    from app.api.predict import get_ml_service as get_service
    return get_service()

class PatientInput(BaseModel):
    age_diagnostic: float = Field(..., ge=0, le=120, example=28)
    cd4_debut: int = Field(..., ge=0, le=2000, example=350)
    score_inf_opp: float = Field(..., ge=0, le=100, example=12.5)
    temps_suivi: float = Field(..., ge=0, example=60)
    stade_avance: bool = False
    non_observant: bool = False
    hospitalisation: bool = False
    tuberculoses: bool = False
    vit_seul: bool = True
    etude_secondaire_ou_plus: bool = True

class ShapExplanationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    prediction: str
    confidence: float
    probabilities: Dict[str, float]
    shap_values: Dict[str, float]
    risk_factors: List[str]
    protective_factors: List[str]
    interpretation: str
    clinical_alert: Optional[str] = None
    waterfall_image_url: Optional[str] = None
    confidence_level: Optional[str] = None

# ============================================================================
# PREDICTION UI - avec bascule de thème (Dark / Light)
# ============================================================================

@router.get("/predict-ui", response_class=HTMLResponse)
async def prediction_ui():
    """Interface utilisateur pour prédiction avec SHAP - thème clair/sombre"""
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Prédiction VIH · Plateforme Clinique</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
        <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,100..900;1,100..900&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
        <style>
            /* ===== VARIABLES THEME ===== */
            :root {
                --bg-primary: #f5f7fa;
                --bg-secondary: #ffffff;
                --bg-card: #ffffff;
                --bg-header: #eef2f7;
                --bg-input: #ffffff;
                --bg-checkbox: #f0f4f9;
                --text-primary: #1e2a3e;
                --text-secondary: #4a5b72;
                --text-muted: #7a8ca0;
                --border-color: #dce3ed;
                --shadow: 0 8px 30px rgba(0,0,0,0.08);
                --shadow-hover: 0 12px 40px rgba(0,0,0,0.12);
                --accent: #1f6392;
                --accent-light: #e6f0fa;
                --accent-dark: #134b6f;
                --success: #27ae60;
                --danger: #e74c3c;
                --warning: #f39c12;
                --risk-bg: #fee2e2;
                --risk-text: #b91c1c;
                --protective-bg: #e0f2e9;
                --protective-text: #0f6e3f;
                --banner-bg: #fff8e7;
                --banner-border: #f39c12;
                --banner-text: #7a6a2e;
                --radius: 24px;
                --transition: 0.3s ease;
            }

            /* Dark theme */
            [data-theme="dark"] {
                --bg-primary: #0b0e14;
                --bg-secondary: #141c26;
                --bg-card: #141c26;
                --bg-header: #1a2330;
                --bg-input: #1e2836;
                --bg-checkbox: #1a2330;
                --text-primary: #e8edf3;
                --text-secondary: #b0c8e0;
                --text-muted: #7a92b0;
                --border-color: #2a364a;
                --shadow: 0 8px 28px rgba(0,0,0,0.5);
                --shadow-hover: 0 12px 40px rgba(0,0,0,0.7);
                --accent: #2a7de1;
                --accent-light: #1e2a3a;
                --accent-dark: #15529a;
                --risk-bg: #3e1a1a;
                --risk-text: #f5a0a0;
                --protective-bg: #1a3a2a;
                --protective-text: #8cd4b0;
                --banner-bg: #1e2a3a;
                --banner-border: #f1c40f;
                --banner-text: #e8d8b0;
            }

            /* ===== RESET & BASE ===== */
            * { margin:0; padding:0; box-sizing:border-box; }
            body {
                font-family: 'Inter', sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                padding: 24px 20px;
                min-height: 100vh;
                transition: background var(--transition), color var(--transition);
            }
            .container { max-width:1500px; margin:0 auto; }

            /* ===== TOGGLE THEME ===== */
            .theme-toggle {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 999;
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: 40px;
                padding: 8px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                cursor: pointer;
                box-shadow: var(--shadow);
                transition: all var(--transition);
                color: var(--text-primary);
                font-size: 0.85rem;
                font-weight: 500;
            }
            .theme-toggle i {
                font-size: 1.2rem;
                color: var(--accent);
            }
            .theme-toggle:hover {
                transform: scale(1.03);
                box-shadow: var(--shadow-hover);
            }

            /* ===== HEADER ===== */
            .medical-header {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: var(--radius);
                padding: 24px 32px;
                margin-bottom: 28px;
                box-shadow: var(--shadow);
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
                align-items: center;
                transition: all var(--transition);
            }
            .hospital-badge {
                display: flex;
                align-items: center;
                gap: 16px;
            }
            .hospital-badge i {
                font-size: 2.4rem;
                background: var(--accent-light);
                padding: 14px;
                border-radius: 20px;
                color: var(--accent);
            }
            .hospital-badge h1 {
                font-size: 1.8rem;
                font-weight: 600;
                letter-spacing: -0.5px;
                color: var(--text-primary);
            }
            .hospital-badge span {
                background: var(--accent-light);
                padding: 4px 14px;
                border-radius: 40px;
                font-size: 0.75rem;
                font-weight: 500;
                color: var(--accent);
            }
            .header-stats {
                display: flex;
                gap: 20px;
                font-size: 0.8rem;
                color: var(--text-secondary);
            }
            .header-stats i { margin-right:6px; color:var(--accent); }

            .clinical-banner {
                background: var(--banner-bg);
                border-left: 4px solid var(--banner-border);
                border-radius: 16px;
                padding: 14px 22px;
                margin-bottom: 24px;
                display: flex;
                align-items: center;
                gap: 14px;
                color: var(--banner-text);
                font-size: 0.85rem;
                box-shadow: var(--shadow);
            }
            .clinical-banner i { font-size:1.4rem; color:var(--banner-border); }

            /* ===== GRID ===== */
            .main-grid {
                display: flex;
                flex-wrap: wrap;
                gap: 30px;
            }
            .form-card, .result-card-new {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: var(--radius);
                box-shadow: var(--shadow);
                flex:1;
                min-width:320px;
                overflow:hidden;
                transition: all var(--transition);
            }
            .card-header {
                background: var(--bg-header);
                padding: 18px 24px;
                border-bottom: 1px solid var(--border-color);
                font-weight: 600;
                font-size:1.1rem;
                color: var(--text-primary);
                display:flex;
                align-items:center;
                gap:12px;
            }
            .card-header i { color:var(--accent); font-size:1.2rem; }
            .form-body { padding:24px; }

            /* ===== FORM ===== */
            .input-group {
                margin-bottom: 18px;
            }
            .input-group label {
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 500;
                font-size:0.8rem;
                color: var(--text-secondary);
                margin-bottom:6px;
            }
            .input-group label i { color:var(--accent); width:18px; }
            .input-group input, .input-group select {
                width:100%;
                padding:12px 14px;
                background: var(--bg-input);
                border:1px solid var(--border-color);
                border-radius:16px;
                color: var(--text-primary);
                font-size:0.9rem;
                transition:0.2s;
                font-family:'Inter', monospace;
            }
            .input-group input:focus, .input-group select:focus {
                border-color: var(--accent);
                outline:none;
                box-shadow: 0 0 0 3px rgba(31,99,146,0.15);
            }
            .input-group small { color:var(--text-muted); font-size:0.7rem; }

            .checkbox-cluster {
                display: flex;
                flex-wrap: wrap;
                gap:12px;
                margin-top:8px;
                background: var(--bg-checkbox);
                padding:12px 16px;
                border-radius:20px;
                border:1px solid var(--border-color);
            }
            .checkbox-item {
                display:flex;
                align-items:center;
                gap:8px;
                font-size:0.8rem;
                cursor:pointer;
                background: var(--bg-input);
                padding:6px 14px;
                border-radius:40px;
                border:1px solid var(--border-color);
                transition:0.15s;
                color: var(--text-secondary);
            }
            .checkbox-item input {
                width:16px; height:16px; accent-color:var(--accent); margin:0;
            }
            .checkbox-item:hover {
                background: var(--bg-header);
                border-color: var(--accent);
            }

            /* ===== BUTTONS ===== */
            .btn-medical {
                background: linear-gradient(145deg, var(--accent), var(--accent-dark));
                width:100%;
                padding:14px;
                border:none;
                border-radius:40px;
                color:white;
                font-weight:700;
                font-size:1rem;
                margin-top:20px;
                cursor:pointer;
                display:flex;
                align-items:center;
                justify-content:center;
                gap:10px;
                transition:0.2s;
                box-shadow: 0 4px 12px rgba(31,99,146,0.25);
            }
            .btn-medical:hover {
                transform:translateY(-2px);
                box-shadow: 0 6px 18px rgba(31,99,146,0.35);
            }

            .btn-export {
                background: var(--success);
                width:100%;
                padding:12px;
                border:none;
                border-radius:40px;
                color:white;
                font-weight:600;
                font-size:0.9rem;
                margin-top:12px;
                cursor:pointer;
                display:flex;
                align-items:center;
                justify-content:center;
                gap:8px;
                transition:0.2s;
            }
            .btn-export:hover {
                transform:translateY(-2px);
                opacity:0.9;
            }

            /* ===== RESULT ===== */
            .result-badge {
                background: var(--bg-header);
                padding:20px;
                border-radius:24px;
                text-align:center;
                margin:20px;
                border:1px solid var(--border-color);
            }
            .outcome {
                font-size:2.2rem;
                font-weight:800;
                letter-spacing:-0.5px;
                margin:10px 0;
            }
            .confidence-pill {
                display:inline-block;
                background: var(--bg-input);
                padding:4px 16px;
                border-radius:50px;
                font-size:0.8rem;
                font-weight:500;
                color: var(--text-secondary);
                border:1px solid var(--border-color);
            }
            .shap-table {
                width:100%;
                border-collapse:collapse;
                font-size:0.8rem;
            }
            .shap-table td {
                padding:8px 6px;
                border-bottom:1px solid var(--border-color);
                color: var(--text-primary);
            }
            .risk-badge {
                background: var(--risk-bg);
                color: var(--risk-text);
                border-radius:40px;
                padding:2px 12px;
                font-size:0.7rem;
                font-weight:600;
                display:inline-block;
            }
            .protective-badge {
                background: var(--protective-bg);
                color: var(--protective-text);
                border-radius:40px;
                padding:2px 12px;
                font-size:0.7rem;
                font-weight:600;
                display:inline-block;
            }

            .footer-note {
                font-size:0.7rem;
                text-align:center;
                margin-top:24px;
                color: var(--text-muted);
                border-top:1px solid var(--border-color);
                padding-top:16px;
            }

            /* ===== SPINNER ===== */
            .spinner { color:var(--accent); font-size:2.2rem; }

            /* ===== RESPONSIVE ===== */
            @media (max-width:850px) {
                body { padding:12px; }
                .medical-header { padding:18px; flex-direction:column; align-items:flex-start; gap:12px; }
                .theme-toggle { top:10px; right:10px; padding:6px 12px; font-size:0.75rem; }
            }
        </style>
    </head>
    <body>

        <!-- BOUTON DE BASCULE -->
        <div class="theme-toggle" onclick="toggleTheme()" title="Basculer le thème">
            <i id="themeIcon" class="fas fa-moon"></i>
            <span id="themeLabel">Sombre</span>
        </div>

        <div class="container">
            <!-- HEADER -->
            <div class="medical-header">
                <div class="hospital-badge">
                    <i class="fas fa-hospital-user"></i>
                    <h1>Service Immuno-VIH</h1>
                    <span>Prédiction clinique</span>
                </div>
                <div class="header-stats">
                    <span><i class="fas fa-chart-line"></i> Fine-Gray / RF</span>
                    <span><i class="fas fa-database"></i> 4 issues</span>
                    <span><i class="fas fa-microscope"></i> SHAP explainable</span>
                </div>
            </div>

            <div class="clinical-banner">
                <i class="fas fa-shield-alt"></i>
                <span>Outil d'aide à la décision clinique – résultats à interpréter par un médecin.</span>
            </div>

            <div class="main-grid">
                <!-- FORMULAIRE -->
                <div class="form-card">
                    <div class="card-header">
                        <i class="fas fa-notes-medical"></i> Dossier patient
                    </div>
                    <div class="form-body">
                        <div class="input-group">
                            <label for="date_naissance"><i class="fas fa-calendar-alt"></i> Date de naissance</label>
                            <input type="date" id="date_naissance" required>
                        </div>
                        <div class="input-group">
                            <label for="date_seropositivite"><i class="fas fa-calendar-check"></i> Date de séropositivité</label>
                            <input type="date" id="date_seropositivite" required>
                        </div>
                        <div class="input-group">
                            <label for="date_derniere_observation"><i class="fas fa-clock"></i> Date de dernière observation</label>
                            <input type="date" id="date_derniere_observation" required>
                        </div>
                        <div id="datesError" role="alert" style="display:none; color:var(--danger); margin-bottom:12px;"></div>
                        <div class="input-group">
                            <label for="age_diagnostic"><i class="fas fa-user-clock"></i> Âge au diagnostic (années)</label>
                            <input type="number" id="age_diagnostic" step="0.01" readonly>
                        </div>
                        <div class="input-group">
                            <label><i class="fas fa-tint"></i> CD4 (cellules/mm³)</label>
                            <input type="number" id="cd4_debut" value="700" step="10">
                        </div>
                        <div class="input-group">
                            <label><i class="fas fa-virus"></i> Score IO (0-6)</label>
                            <input type="number" id="score_inf_opp" value="0" step="0.5">
                        </div>
                        <div class="input-group">
                            <label for="temps_suivi"><i class="fas fa-hourglass-half"></i> Durée du suivi (mois)</label>
                            <input type="number" id="temps_suivi" step="0.01" readonly>
                            <small>Calculée automatiquement entre la séropositivité et la dernière observation.</small>
                        </div>

                        <div style="font-weight:500; margin:12px 0 6px 0; color:var(--text-secondary);">
                            <i class="fas fa-stethoscope"></i> Antécédents cliniques
                        </div>
                        <div class="checkbox-cluster" id="risk-factors-group">
                            <label class="checkbox-item"><input type="checkbox" id="stade_avance"> Stade avancé (OMS III/IV)</label>
                            <label class="checkbox-item"><input type="checkbox" id="non_observant"> Non-observance</label>
                            <label class="checkbox-item"><input type="checkbox" id="hospitalisation"> Hospitalisation antérieure</label>
                            <label class="checkbox-item"><input type="checkbox" id="tuberculoses"> Tuberculose</label>
                            <label class="checkbox-item"><input type="checkbox" id="vit_seul"> Vit seul</label>
                            <label class="checkbox-item"><input type="checkbox" id="etude_secondaire_ou_plus"> Étude secondaire+</label>
                        </div>

                        <button class="btn-medical" onclick="predict()"><i class="fas fa-chart-simple"></i> ANALYSE PRONOSTIC</button>
                        <button class="btn-export" onclick="exportData()">
                            <i class="fas fa-download"></i> Exporter les données (CSV)
                        </button>
                    </div>
                </div>

                <!-- RÉSULTAT -->
                <div class="result-card-new" id="resultPanel">
                    <div class="card-header">
                        <i class="fas fa-file-waveform"></i> Résultat de l'évaluation
                    </div>
                    <div id="loading" style="display:none; text-align:center; padding:60px 20px;">
                        <i class="fas fa-spinner fa-pulse spinner"></i>
                        <p style="margin-top:12px; color:var(--text-muted);">Analyse en cours...</p>
                    </div>
                    <div id="resultContent">
                        <div class="result-badge" style="text-align:center;">
                            <i class="fas fa-stethoscope" style="font-size:2.4rem; opacity:0.3;"></i>
                            <p style="margin-top:12px; color:var(--text-muted);">Remplissez le formulaire<br>et lancez l'analyse</p>
                        </div>
                    </div>
                    <div class="footer-note">
                        <i class="fas fa-chart-line"></i> Interprétation SHAP · Facteurs de risque / protecteurs
                    </div>
                </div>
            </div>
        </div>

        <script>
            // ===== GESTION DU THÈME =====
            function getPreferredTheme() {
                return localStorage.getItem('theme') || 'light';
            }

            function setTheme(theme) {
                document.documentElement.setAttribute('data-theme', theme);
                localStorage.setItem('theme', theme);
                const icon = document.getElementById('themeIcon');
                const label = document.getElementById('themeLabel');
                if (theme === 'dark') {
                    icon.className = 'fas fa-sun';
                    label.textContent = 'Clair';
                } else {
                    icon.className = 'fas fa-moon';
                    label.textContent = 'Sombre';
                }
            }

            function toggleTheme() {
                const current = document.documentElement.getAttribute('data-theme') || 'light';
                const next = current === 'dark' ? 'light' : 'dark';
                setTheme(next);
            }

            // Appliquer le thème au chargement
            (function() {
                const preferred = getPreferredTheme();
                setTheme(preferred);
            })();

            const dateFields = [
                document.getElementById('date_naissance'),
                document.getElementById('date_seropositivite'),
                document.getElementById('date_derniere_observation')
            ];

            function localDateString(date) {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            }

            function dateToUtcDays(value) {
                const [year, month, day] = value.split('-').map(Number);
                return Date.UTC(year, month - 1, day) / 86400000;
            }

            function updateDerivedDates() {
                const [birthDate, seropositivityDate, lastObservationDate] =
                    dateFields.map(field => field.value);
                const error = document.getElementById('datesError');
                const ageField = document.getElementById('age_diagnostic');
                const followUpField = document.getElementById('temps_suivi');
                const today = localDateString(new Date());

                dateFields.forEach(field => { field.max = today; });
                dateFields[1].min = birthDate || '';
                dateFields[2].min = seropositivityDate || '';

                let message = '';
                if (!birthDate || !seropositivityDate || !lastObservationDate) {
                    message = 'Renseignez les trois dates pour calculer l’âge et la durée du suivi.';
                } else if (birthDate > seropositivityDate) {
                    message = 'La date de naissance doit précéder la date de séropositivité.';
                } else if (seropositivityDate > lastObservationDate) {
                    message = 'La dernière observation doit être postérieure ou égale à la séropositivité.';
                } else if (lastObservationDate > today) {
                    message = 'La date de dernière observation ne peut pas être dans le futur.';
                }

                if (message) {
                    ageField.value = '';
                    followUpField.value = '';
                    error.textContent = message;
                    error.style.display = 'block';
                    return null;
                }

                const ageInDays = dateToUtcDays(seropositivityDate) - dateToUtcDays(birthDate);
                const followUpInDays = dateToUtcDays(lastObservationDate) - dateToUtcDays(seropositivityDate);
                const ageDiagnostic = ageInDays / 365.25;
                const followUpMonths = followUpInDays / 30.44;
                ageField.value = ageDiagnostic.toFixed(2);
                followUpField.value = followUpMonths.toFixed(2);
                error.textContent = '';
                error.style.display = 'none';
                return { ageDiagnostic, followUpMonths };
            }

            dateFields.forEach(field => field.addEventListener('change', updateDerivedDates));
            updateDerivedDates();

            // ===== FONCTIONS DE PRÉDICTION =====
            async function predict() {
                const derivedDates = updateDerivedDates();
                if (!derivedDates) {
                    return;
                }

                const patient = {
                    age_diagnostic: derivedDates.ageDiagnostic,
                    cd4_debut: parseInt(document.getElementById('cd4_debut').value) || 0,
                    score_inf_opp: parseFloat(document.getElementById('score_inf_opp').value) || 0,
                    temps_suivi: derivedDates.followUpMonths,
                    stade_avance: document.getElementById('stade_avance').checked,
                    non_observant: document.getElementById('non_observant').checked,
                    hospitalisation: document.getElementById('hospitalisation').checked,
                    tuberculoses: document.getElementById('tuberculoses').checked,
                    vit_seul: document.getElementById('vit_seul').checked,
                    etude_secondaire_ou_plus: document.getElementById('etude_secondaire_ou_plus').checked
                };

                const loadingDiv = document.getElementById('loading');
                const resultDiv = document.getElementById('resultContent');
                loadingDiv.style.display = 'block';
                resultDiv.innerHTML = '';

                try {
                    const response = await fetch('/api/viz/shap-explain', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(patient)
                    });
                    const data = await response.json();
                    if (response.ok) {
                        displayClinicalResult(data);
                    } else {
                        resultDiv.innerHTML = `<div class="result-badge" style="color:var(--danger);">❌ Erreur: ${data.detail || 'Requête invalide'}</div>`;
                    }
                } catch (err) {
                    resultDiv.innerHTML = `<div class="result-badge" style="color:var(--danger);">⚠️ Connexion au serveur impossible</div>`;
                } finally {
                    loadingDiv.style.display = 'none';
                }
            }

            function displayClinicalResult(data) {
                const container = document.getElementById('resultContent');
                const confidencePercent = (data.confidence * 100).toFixed(1);
                let outcomeColor = 'var(--accent)';
                if (data.prediction === 'Décédé') outcomeColor = 'var(--danger)';
                else if (data.prediction === 'Perdu de Vue') outcomeColor = 'var(--warning)';
                else if (data.prediction === 'Vivant') outcomeColor = 'var(--success)';

                let alertHtml = '';
                if (data.clinical_alert) {
                    alertHtml = `<div style="background:var(--banner-bg); border-left:4px solid var(--banner-border); padding:12px; border-radius:16px; margin-top:12px; font-size:0.8rem; color:var(--banner-text);">⚠️ ${data.clinical_alert}</div>`;
                }

                const outcomeNames = ['Décédé', 'Perdu de Vue', 'Transféré', 'Vivant'];
                const probabilityRows = outcomeNames.map(name => {
                    const probability = data.probabilities[name];
                    if (typeof probability !== 'number' || !Number.isFinite(probability)) {
                        return `<div style="display:flex; justify-content:space-between;"><span>${name}</span><span>—</span></div>`;
                    }
                    const percentage = probability * 100;
                    const barWidth = Math.max(0, Math.min(percentage, 100));
                    return `<div style="margin-top:8px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.8rem;"><span>${name}</span><strong>${percentage.toFixed(1)}%</strong></div>
                        <div style="height:7px; background:var(--border-color); border-radius:8px; overflow:hidden;"><div style="height:100%; width:${barWidth}%; background:var(--accent);"></div></div>
                    </div>`;
                }).join('');

                const classConfig = {
                    "Vivant": { positive: 'protective', negative: 'risk' },
                    "Décédé": { positive: 'risk', negative: 'protective' },
                    "Perdu de Vue": { positive: 'risk', negative: 'protective' },
                    "Transféré": { positive: 'risk', negative: 'protective' }
                };
                const config = classConfig[data.prediction] || { positive: 'risk', negative: 'protective' };

                let shapRows = '';
                const sortedEntries = Object.entries(data.shap_values).sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]));
                for (const [feat, val] of sortedEntries.slice(0,8)) {
                    let direction, badgeClass;
                    if (val > 0) {
                        if (config.positive === 'protective') {
                            direction = '↓ risque (protecteur)';
                            badgeClass = 'protective-badge';
                        } else {
                            direction = '↑ risque';
                            badgeClass = 'risk-badge';
                        }
                    } else {
                        if (config.negative === 'protective') {
                            direction = '↓ risque (protecteur)';
                            badgeClass = 'protective-badge';
                        } else {
                            direction = '↑ risque';
                            badgeClass = 'risk-badge';
                        }
                    }
                    shapRows += `<tr><td>${feat}</td><td>${val > 0 ? '+' : ''}${val.toFixed(3)}</td><td><span class="${badgeClass}">${direction}</span></td></tr>`;
                }

                const riskListHtml = data.risk_factors.map(f => `<span class="risk-badge" style="display:inline-block; margin:2px;">${f}</span>`).join('');
                const protectiveListHtml = data.protective_factors.map(f => `<span class="protective-badge" style="display:inline-block; margin:2px;">${f}</span>`).join('');

                const html = `
                    <div class="result-badge">
                        <div style="font-size:0.7rem; letter-spacing:1px; color:var(--text-muted);">PRONOSTIC PRINCIPAL</div>
                        <div class="outcome" style="color:${outcomeColor};">${data.prediction}</div>
                        <div><span class="confidence-pill">🔍 Confiance ${confidencePercent}%</span></div>
                        ${alertHtml}
                        <div style="margin-top:15px; font-size:0.85rem; background:var(--bg-input); border-radius:20px; padding:14px; text-align:left; color:var(--text-primary);">
                            <strong><i class="fas fa-chart-pie" style="color:var(--accent);"></i> Probabilités des 4 trajectoires</strong>
                            ${probabilityRows}
                        </div>
                        <div style="margin-top:15px; font-size:0.85rem; background:var(--bg-input); border-radius:20px; padding:14px; text-align:left; color:var(--text-primary);">
                            <i class="fas fa-comment-medical" style="color:var(--accent);"></i> <strong>Interprétation clinique</strong><br>${data.interpretation}
                        </div>
                    </div>
                    <div style="padding:10px 20px;">
                        <div style="display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px;">
                            <div style="flex:1;"><i class="fas fa-exclamation-triangle" style="color:var(--danger);"></i> <strong style="color:var(--text-primary);">Facteurs de risque</strong><br>${riskListHtml || '—'}</div>
                            <div style="flex:1;"><i class="fas fa-leaf" style="color:var(--success);"></i> <strong style="color:var(--text-primary);">Facteurs protecteurs</strong><br>${protectiveListHtml || '—'}</div>
                        </div>
                        <div><strong style="color:var(--text-primary);"><i class="fas fa-chart-simple" style="color:var(--accent);"></i> Contributions SHAP</strong>
                            <table class="shap-table" style="width:100%; margin-top:8px;">${shapRows}</table>
                        </div>
                        ${data.waterfall_image_url ? `<div style="margin-top:20px;"><img src="${data.waterfall_image_url}" style="width:100%; border-radius:20px; border:1px solid var(--border-color);"></div>` : ''}
                    </div>
                `;
                container.innerHTML = html;
            }

            function exportData() {
                window.location.href = '/api/export/predictions?format=csv';
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ============================================================================
# DASHBOARD CRUD - avec bascule de thème (Dark / Light)
# ============================================================================

@router.get("/dashboard-crud", response_class=HTMLResponse)
async def dashboard_crud(request: Request):
    """Interface Dashboard CRUD avec authentification - thème clair/sombre"""
    
    print("=" * 60)
    print("🔍 DASHBOARD CRUD - VÉRIFICATION D'AUTHENTIFICATION")
    print(f"📋 Cookies reçus: {request.cookies}")
    print(f"📋 Query params: {request.query_params}")
    print("=" * 60)
    
    token = request.query_params.get("token")
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    if not token:
        print("❌ Pas de token trouvé - Redirection vers login")
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        from jose import jwt
        import os
        from dotenv import load_dotenv
        load_dotenv()
        SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ma_super_cle_secrete_pour_jwt_2024_change_me")
        ALGORITHM = "HS256"
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            print("❌ Token invalide - Pas d'username")
            return RedirectResponse(url="/login", status_code=302)
        print(f"✅ Utilisateur authentifié: {username}")
    except Exception as e:
        print(f"❌ Token invalide: {e}")
        return RedirectResponse(url="/login", status_code=302)
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard CRUD · VIH</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
        <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,100..900;1,100..900&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
        <style>
            /* ===== VARIABLES THEME ===== */
            :root {
                --bg-primary: #f5f7fa;
                --bg-secondary: #ffffff;
                --bg-card: #ffffff;
                --bg-header: #eef2f7;
                --bg-input: #ffffff;
                --bg-table-hover: #f0f4f9;
                --text-primary: #1e2a3e;
                --text-secondary: #4a5b72;
                --text-muted: #7a8ca0;
                --border-color: #dce3ed;
                --shadow: 0 4px 16px rgba(0,0,0,0.06);
                --shadow-hover: 0 8px 28px rgba(0,0,0,0.10);
                --accent: #1f6392;
                --accent-light: #e6f0fa;
                --accent-dark: #134b6f;
                --success: #27ae60;
                --danger: #e74c3c;
                --warning: #f39c12;
                --risk-bg: #fee2e2;
                --risk-text: #b91c1c;
                --protective-bg: #e0f2e9;
                --protective-text: #0f6e3f;
                --radius: 20px;
                --transition: 0.3s ease;
            }

            [data-theme="dark"] {
                --bg-primary: #0b0e14;
                --bg-secondary: #141c26;
                --bg-card: #141c26;
                --bg-header: #1a2330;
                --bg-input: #1e2836;
                --bg-table-hover: #1a2330;
                --text-primary: #e8edf3;
                --text-secondary: #b0c8e0;
                --text-muted: #7a92b0;
                --border-color: #2a364a;
                --shadow: 0 4px 16px rgba(0,0,0,0.4);
                --shadow-hover: 0 8px 28px rgba(0,0,0,0.6);
                --accent: #2a7de1;
                --accent-light: #1e2a3a;
                --accent-dark: #15529a;
                --risk-bg: #3e1a1a;
                --risk-text: #f5a0a0;
                --protective-bg: #1a3a2a;
                --protective-text: #8cd4b0;
            }

            /* ===== RESET ===== */
            * { margin:0; padding:0; box-sizing:border-box; }
            body {
                font-family: 'Inter', sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                padding: 20px;
                min-height: 100vh;
                transition: background var(--transition), color var(--transition);
            }
            .container { max-width:1600px; margin:0 auto; }

            /* ===== TOGGLE ===== */
            .theme-toggle {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 999;
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: 40px;
                padding: 8px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
                cursor: pointer;
                box-shadow: var(--shadow);
                transition: all var(--transition);
                color: var(--text-primary);
                font-size: 0.85rem;
                font-weight: 500;
            }
            .theme-toggle i {
                font-size: 1.2rem;
                color: var(--accent);
            }
            .theme-toggle:hover {
                transform: scale(1.03);
                box-shadow: var(--shadow-hover);
            }

            /* ===== HEADER ===== */
            .dashboard-header {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: var(--radius);
                padding: 20px 30px;
                margin-bottom: 28px;
                box-shadow: var(--shadow);
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 16px;
                transition: all var(--transition);
            }
            .header-title h1 {
                font-size: 1.6rem;
                font-weight: 600;
                color: var(--text-primary);
            }
            .header-title p {
                opacity: 0.7;
                font-size: 0.85rem;
                color: var(--text-secondary);
            }
            .header-stats {
                display: flex;
                gap: 20px;
            }
            .stat-box {
                background: var(--bg-header);
                border: 1px solid var(--border-color);
                padding: 8px 18px;
                border-radius: 16px;
                text-align: center;
                min-width: 80px;
            }
            .stat-box .number {
                font-size: 1.8rem;
                font-weight: 700;
                color: var(--text-primary);
            }
            .stat-box .label {
                font-size: 0.65rem;
                opacity: 0.6;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            /* ===== TABS ===== */
            .nav-tabs {
                display: flex;
                gap: 12px;
                margin-bottom: 28px;
                background: var(--bg-card);
                padding: 6px 12px;
                border-radius: 60px;
                border: 1px solid var(--border-color);
                width: fit-content;
                box-shadow: var(--shadow);
            }
            .nav-tab {
                padding: 10px 24px;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font-weight: 500;
                border-radius: 40px;
                transition: 0.2s;
                font-size: 0.9rem;
            }
            .nav-tab:hover { background: var(--bg-header); color: var(--text-primary); }
            .nav-tab.active {
                background: var(--accent);
                color: white;
                box-shadow: 0 2px 8px rgba(31,99,146,0.2);
            }

            /* ===== CARDS ===== */
            .card {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: var(--radius);
                overflow: hidden;
                margin-bottom: 28px;
                box-shadow: var(--shadow);
                transition: all var(--transition);
            }
            .card-header {
                background: var(--bg-header);
                padding: 14px 24px;
                border-bottom: 1px solid var(--border-color);
                font-weight: 600;
                color: var(--text-primary);
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 10px;
            }
            .card-body { padding: 20px; }

            /* ===== TABLE ===== */
            .data-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 0.8rem;
                color: var(--text-primary);
            }
            .data-table th {
                background: var(--bg-header);
                padding: 12px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid var(--border-color);
                color: var(--text-secondary);
            }
            .data-table td {
                padding: 10px 12px;
                border-bottom: 1px solid var(--border-color);
            }
            .data-table tr:hover { background: var(--bg-table-hover); }

            /* ===== BUTTONS ===== */
            .btn {
                padding: 8px 16px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-size: 0.8rem;
                font-weight: 500;
                transition: 0.2s;
                display: inline-flex;
                align-items: center;
                gap: 6px;
            }
            .btn-primary {
                background: var(--accent);
                color: white;
            }
            .btn-primary:hover {
                background: var(--accent-dark);
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(31,99,146,0.2);
            }
            .btn-danger {
                background: var(--danger);
                color: white;
            }
            .btn-danger:hover {
                opacity: 0.85;
                transform: translateY(-2px);
            }
            .btn-sm { padding: 4px 12px; font-size: 0.7rem; }

            .btn-logout {
                position: fixed;
                top: 80px;
                right: 20px;
                background: var(--danger);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 12px;
                cursor: pointer;
                font-weight: 600;
                z-index: 1000;
                display: flex;
                align-items: center;
                gap: 8px;
                box-shadow: var(--shadow);
                transition: 0.2s;
            }
            .btn-logout:hover { opacity:0.85; transform:translateY(-2px); }

            /* ===== FILTERS ===== */
            .filters-bar {
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
                align-items: center;
            }
            .filter-select, .filter-input {
                padding: 8px 14px;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                color: var(--text-primary);
                font-size: 0.8rem;
                transition: 0.2s;
            }
            .filter-select:focus, .filter-input:focus {
                border-color: var(--accent);
                outline: none;
                box-shadow: 0 0 0 3px rgba(31,99,146,0.15);
            }

            /* ===== MODAL ===== */
            .modal {
                display: none;
                position: fixed;
                top:0; left:0; width:100%; height:100%;
                background: rgba(0,0,0,0.5);
                z-index: 2000;
                justify-content: center;
                align-items: center;
            }
            .modal.active { display: flex; }
            .modal-content {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: 24px;
                width: 90%;
                max-width: 600px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: var(--shadow-hover);
            }
            .modal-header {
                padding: 16px 20px;
                border-bottom: 1px solid var(--border-color);
                display: flex;
                justify-content: space-between;
                align-items: center;
                color: var(--text-primary);
            }
            .modal-body { padding: 20px; }
            .modal-footer {
                padding: 16px 20px;
                border-top: 1px solid var(--border-color);
                display: flex;
                justify-content: flex-end;
                gap: 12px;
            }
            .form-group {
                margin-bottom: 16px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 500;
                font-size: 0.8rem;
                color: var(--text-secondary);
            }
            .form-group input, .form-group select {
                width:100%;
                padding:10px 14px;
                background: var(--bg-input);
                border:1px solid var(--border-color);
                border-radius:12px;
                color: var(--text-primary);
                font-size:0.9rem;
            }
            .form-group input:focus, .form-group select:focus {
                border-color: var(--accent);
                outline:none;
                box-shadow: 0 0 0 3px rgba(31,99,146,0.15);
            }

            /* ===== PAGINATION ===== */
            .pagination {
                display: flex;
                justify-content: center;
                gap: 8px;
                margin-top: 20px;
            }
            .pagination button {
                padding: 6px 14px;
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                color: var(--text-secondary);
                border-radius: 8px;
                cursor: pointer;
                transition: 0.15s;
            }
            .pagination button.active {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }
            .pagination button:hover {
                background: var(--bg-header);
            }

            .risk-badge {
                background: var(--risk-bg);
                color: var(--risk-text);
                border-radius: 40px;
                padding: 2px 14px;
                font-size: 0.7rem;
                font-weight: 600;
                display: inline-block;
            }

            /* ===== RESPONSIVE ===== */
            @media (max-width: 768px) {
                .data-table { font-size:0.7rem; }
                .btn-sm { padding:2px 8px; }
                .header-stats { gap:10px; flex-wrap:wrap; }
                .theme-toggle { top:10px; right:10px; padding:6px 12px; font-size:0.75rem; }
                .btn-logout { top:70px; right:10px; padding:6px 14px; font-size:0.8rem; }
            }
        </style>
    </head>
    <body>

        <!-- BOUTON DE BASCULE -->
        <div class="theme-toggle" onclick="toggleTheme()" title="Basculer le thème">
            <i id="themeIcon" class="fas fa-moon"></i>
            <span id="themeLabel">Sombre</span>
        </div>

        <button class="btn-logout" onclick="logout()">
            <i class="fas fa-sign-out-alt"></i> Déconnexion
        </button>

        <div class="container">
            <!-- HEADER -->
            <div class="dashboard-header">
                <div class="header-title">
                    <h1><i class="fas fa-chalkboard-user" style="color:var(--accent);"></i> Dashboard CRUD</h1>
                    <p>Gestion complète des prédictions patients VIH</p>
                </div>
                <div class="header-stats" id="headerStats">
                    <div class="stat-box">
                        <div class="number" id="totalCount">-</div>
                        <div class="label">Total</div>
                    </div>
                    <div class="stat-box">
                        <div class="number" id="todayCount">-</div>
                        <div class="label">Aujourd'hui</div>
                    </div>
                    <div class="stat-box">
                        <div class="number" id="lowConfidenceCount">-</div>
                        <div class="label">Confiance < 50%</div>
                    </div>
                </div>
            </div>

            <!-- TABS -->
            <div class="nav-tabs">
                <button class="nav-tab active" onclick="showTab('list')">
                    <i class="fas fa-list"></i> Liste
                </button>
                <button class="nav-tab" onclick="showTab('stats')">
                    <i class="fas fa-chart-pie"></i> Statistiques
                </button>
                <button class="nav-tab" onclick="showTab('export')">
                    <i class="fas fa-download"></i> Export avancé
                </button>
            </div>

            <!-- TAB LISTE -->
            <div id="listTab" class="tab-content">
                <div class="card">
                    <div class="card-header">
                        <span><i class="fas fa-filter"></i> Filtres</span>
                        <div class="filters-bar">
                            <select id="filterClass" class="filter-select" onchange="loadPredictions()">
                                <option value="">Toutes classes</option>
                                <option value="Décédé">Décédé</option>
                                <option value="Perdu de Vue">Perdu de Vue</option>
                                <option value="Transféré">Transféré</option>
                                <option value="Vivant">Vivant</option>
                            </select>
                            <input type="date" id="filterDate" class="filter-input" onchange="loadPredictions()">
                            <button class="btn btn-primary btn-sm" onclick="loadPredictions()">
                                <i class="fas fa-search"></i> Filtrer
                            </button>
                            <button class="btn btn-primary btn-sm" onclick="openAddModal()">
                                <i class="fas fa-plus"></i> Nouvelle
                            </button>
                        </div>
                    </div>
                    <div class="card-body">
                        <div style="overflow-x:auto;">
                            <table class="data-table" id="predictionsTable">
                                <thead>
                                    <tr>
                                        <th>ID</th><th>Date</th><th>Âge</th><th>CD4</th>
                                        <th>Prédiction</th><th>Confiance</th><th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="tableBody">
                                    <tr><td colspan="7" style="text-align:center; color:var(--text-muted);">Chargement...</td></tr>
                                </tbody>
                            </table>
                        </div>
                        <div class="pagination" id="pagination"></div>
                    </div>
                </div>
            </div>

            <!-- TAB STATS -->
            <div id="statsTab" class="tab-content" style="display:none;">
                <div class="card">
                    <div class="card-header">
                        <span><i class="fas fa-chart-bar"></i> Distribution des prédictions</span>
                    </div>
                    <div class="card-body" id="statsChart" style="height:auto; min-height:300px;"></div>
                </div>
                <div class="card">
                    <div class="card-header">
                        <span><i class="fas fa-chart-line"></i> Évolution (7 derniers jours)</span>
                    </div>
                    <div class="card-body" id="trendChart" style="height:auto; min-height:200px;"></div>
                </div>
            </div>

            <!-- TAB EXPORT -->
            <div id="exportTab" class="tab-content" style="display:none;">
                <div class="card">
                    <div class="card-header">
                        <span><i class="fas fa-file-export"></i> Export avancé</span>
                    </div>
                    <div class="card-body">
                        <div class="form-group">
                            <label>Format</label>
                            <select id="exportFormat" class="filter-select">
                                <option value="csv">CSV (Excel)</option>
                                <option value="json">JSON</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Classe</label>
                            <select id="exportClass" class="filter-select">
                                <option value="">Toutes</option>
                                <option value="Décédé">Décédé</option>
                                <option value="Perdu de Vue">Perdu de Vue</option>
                                <option value="Transféré">Transféré</option>
                                <option value="Vivant">Vivant</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Période</label>
                            <div style="display:flex; gap:10px;">
                                <input type="date" id="exportStartDate" class="filter-input" style="flex:1;">
                                <span style="color:var(--text-muted);">à</span>
                                <input type="date" id="exportEndDate" class="filter-input" style="flex:1;">
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Limite</label>
                            <input type="number" id="exportLimit" value="1000" class="filter-input">
                        </div>
                        <button class="btn btn-primary" onclick="advancedExport()">
                            <i class="fas fa-download"></i> Télécharger
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- MODAL -->
        <div id="editModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3 id="modalTitle">Ajouter une prédiction</h3>
                    <button class="btn btn-sm" onclick="closeModal()" style="background:transparent; color:var(--text-secondary);">✕</button>
                </div>
                <div class="modal-body">
                    <form id="predictionForm">
                        <input type="hidden" id="editId">
                        <div class="form-group">
                            <label>Âge au diagnostic</label>
                            <input type="number" id="editAge" required>
                        </div>
                        <div class="form-group">
                            <label>CD4 début</label>
                            <input type="number" id="editCD4" required>
                        </div>
                        <div class="form-group">
                            <label>Score infections opportunistes</label>
                            <input type="number" step="0.1" id="editScoreIO" value="0">
                        </div>
                        <div class="form-group">
                            <label>Temps de suivi (mois)</label>
                            <input type="number" id="editTempsSuivi" required>
                        </div>
                        <div class="form-group">
                            <label>Stade avancé</label>
                            <select id="editStadeAvance">
                                <option value="false">Non</option>
                                <option value="true">Oui</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Non-observant</label>
                            <select id="editNonObservant">
                                <option value="false">Non</option>
                                <option value="true">Oui</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Hospitalisation</label>
                            <select id="editHospitalisation">
                                <option value="false">Non</option>
                                <option value="true">Oui</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Tuberculose</label>
                            <select id="editTuberculose">
                                <option value="false">Non</option>
                                <option value="true">Oui</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Vit seul</label>
                            <select id="editVitSeul">
                                <option value="false">Non</option>
                                <option value="true">Oui</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Étude secondaire+</label>
                            <select id="editEtudeSecondaire">
                                <option value="false">Non</option>
                                <option value="true">Oui</option>
                            </select>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="closeModal()" style="background:var(--bg-input); color:var(--text-secondary);">Annuler</button>
                    <button class="btn btn-primary" onclick="savePrediction()">Enregistrer</button>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
            // ===== GESTION DU THÈME =====
            function getPreferredTheme() {
                return localStorage.getItem('theme') || 'light';
            }

            function setTheme(theme) {
                document.documentElement.setAttribute('data-theme', theme);
                localStorage.setItem('theme', theme);
                const icon = document.getElementById('themeIcon');
                const label = document.getElementById('themeLabel');
                if (theme === 'dark') {
                    icon.className = 'fas fa-sun';
                    label.textContent = 'Clair';
                } else {
                    icon.className = 'fas fa-moon';
                    label.textContent = 'Sombre';
                }
            }

            function toggleTheme() {
                const current = document.documentElement.getAttribute('data-theme') || 'light';
                const next = current === 'dark' ? 'light' : 'dark';
                setTheme(next);
            }

            (function() {
                const preferred = getPreferredTheme();
                setTheme(preferred);
            })();

            // ===== LOGOUT =====
            function logout() {
                localStorage.removeItem('access_token');
                document.cookie = 'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
                window.location.href = '/login';
            }

            // ===== TABS =====
            let currentPage = 1;
            let totalPages = 1;

            function showTab(tabName) {
                document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
                document.getElementById(tabName + 'Tab').style.display = 'block';
                document.querySelectorAll('.nav-tab').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
                if (tabName === 'list') loadPredictions();
                if (tabName === 'stats') setTimeout(loadStats, 200);
            }

            // ===== PREDICTIONS =====
            async function loadPredictions() {
                const filterClass = document.getElementById('filterClass').value;
                const filterDate = document.getElementById('filterDate').value;
                let url = '/api/predictions?page=' + currentPage + '&limit=20';
                if (filterClass) url += '&prediction_class=' + encodeURIComponent(filterClass);
                if (filterDate) url += '&date=' + filterDate;
                try {
                    const response = await fetch(url);
                    const data = await response.json();
                    if (response.ok) {
                        displayTable(data.data);
                        updatePagination(data.total, data.page, data.pages);
                        updateHeaderStats(data.stats);
                    }
                } catch (error) {
                    console.error('Erreur:', error);
                }
            }

            function displayTable(predictions) {
                const tbody = document.getElementById('tableBody');
                if (!predictions || predictions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted);">Aucune donnée</td></tr>';
                    return;
                }
                let html = '';
                for (let i = 0; i < predictions.length; i++) {
                    const p = predictions[i];
                    const date = new Date(p.created_at).toLocaleDateString();
                    const confidence = (p.confidence * 100).toFixed(1);
                    html += `
                        <tr>
                            <td>${p.id}</td>
                            <td>${date}</td>
                            <td>${p.age_diagnostic}</td>
                            <td>${p.cd4_debut}</td>
                            <td><span class="risk-badge">${p.predicted_class}</span></td>
                            <td>${confidence}%</td>
                            <td>
                                <button class="btn btn-primary btn-sm" onclick="viewPrediction(${p.id})">
                                    <i class="fas fa-eye"></i>
                                </button>
                                <button class="btn btn-danger btn-sm" onclick="deletePrediction(${p.id})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }
                tbody.innerHTML = html;
            }

            function updatePagination(total, page, pages) {
                totalPages = pages;
                currentPage = page;
                const pagination = document.getElementById('pagination');
                let html = '';
                if (page > 1) html += '<button onclick="goToPage(' + (page - 1) + ')">«</button>';
                for (let i = 1; i <= pages && i <= 10; i++) {
                    const active = i === page ? 'active' : '';
                    html += '<button class="' + active + '" onclick="goToPage(' + i + ')">' + i + '</button>';
                }
                if (page < pages) html += '<button onclick="goToPage(' + (page + 1) + ')">»</button>';
                pagination.innerHTML = html;
            }

            function goToPage(page) {
                currentPage = page;
                loadPredictions();
            }

            async function updateHeaderStats(stats) {
                document.getElementById('totalCount').textContent = stats.total || '-';
                document.getElementById('todayCount').textContent = stats.today || '-';
                document.getElementById('lowConfidenceCount').textContent = stats.low_confidence || '-';
            }

            // ===== STATS (sans Chart.js pour éviter dépendance) =====
            async function loadStats() {
                try {
                    const response = await fetch('/api/predictions/stats');
                    const data = await response.json();
                    const statsContainer = document.getElementById('statsChart');
                    const trendContainer = document.getElementById('trendChart');
                    if (statsContainer) {
                        const parent = statsContainer.parentElement;
                        const newDiv = document.createElement('div');
                        newDiv.style.padding = '20px';
                        let html = '<h3 style="color:var(--text-primary); margin-bottom:16px;"><i class="fas fa-chart-pie" style="color:var(--accent);"></i> Distribution</h3>';
                        const total = data.by_class.reduce((s,c) => s + c.count, 0);
                        data.by_class.forEach(function(c) {
                            const colors = { 'Décédé':'var(--danger)', 'Perdu de Vue':'var(--warning)', 'Transféré':'#3498db', 'Vivant':'var(--success)' };
                            const color = colors[c.name] || 'var(--text-muted)';
                            const percent = ((c.count / total) * 100).toFixed(1);
                            html += `
                                <div style="margin:12px 0;">
                                    <div style="display:flex; justify-content:space-between; margin-bottom:4px; color:var(--text-primary);">
                                        <span><span style="color:${color}; font-weight:bold;">●</span> ${c.name}</span>
                                        <span><strong>${c.count}</strong> (${percent}%)</span>
                                    </div>
                                    <div style="background:var(--bg-input); height:8px; border-radius:4px; overflow:hidden;">
                                        <div style="background:${color}; height:100%; width:${percent}%; border-radius:4px;"></div>
                                    </div>
                                </div>
                            `;
                        });
                        newDiv.innerHTML = html;
                        parent.replaceChild(newDiv, statsContainer);
                    }
                    if (trendContainer) {
                        const parent = trendContainer.parentElement;
                        const newDiv = document.createElement('div');
                        newDiv.style.padding = '20px';
                        let html = '<h3 style="color:var(--text-primary); margin-bottom:16px;"><i class="fas fa-chart-line" style="color:var(--accent);"></i> Évolution (7 derniers jours)</h3>';
                        html += '<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">';
                        data.trend.forEach(function(t) {
                            html += `
                                <div style="display:flex; justify-content:space-between; padding:10px 14px; background:var(--bg-input); border-radius:12px; border-left:4px solid var(--accent); color:var(--text-primary);">
                                    <span>${t.date}</span>
                                    <span><strong>${t.count}</strong></span>
                                </div>
                            `;
                        });
                        html += '</div>';
                        newDiv.innerHTML = html;
                        parent.replaceChild(newDiv, trendContainer);
                    }
                } catch (error) {
                    console.error('Erreur stats:', error);
                }
            }

            // ===== CRUD =====
            function viewPrediction(id) {
                window.open('/api/predictions/' + id, '_blank');
            }

            async function deletePrediction(id) {
                if (confirm('Supprimer cette prédiction ?')) {
                    try {
                        const response = await fetch('/api/predictions/' + id, { method: 'DELETE' });
                        if (response.ok) {
                            loadPredictions();
                            loadStats();
                        }
                    } catch (error) { console.error(error); }
                }
            }

            function openAddModal() {
                document.getElementById('modalTitle').textContent = 'Ajouter une prédiction';
                document.getElementById('editId').value = '';
                document.getElementById('predictionForm').reset();
                document.getElementById('editModal').classList.add('active');
            }

            function closeModal() {
                document.getElementById('editModal').classList.remove('active');
            }

            async function savePrediction() {
                const data = {
                    age_diagnostic: parseInt(document.getElementById('editAge').value),
                    cd4_debut: parseInt(document.getElementById('editCD4').value),
                    score_inf_opp: parseFloat(document.getElementById('editScoreIO').value),
                    temps_suivi: parseInt(document.getElementById('editTempsSuivi').value),
                    stade_avance: document.getElementById('editStadeAvance').value === 'true',
                    non_observant: document.getElementById('editNonObservant').value === 'true',
                    hospitalisation: document.getElementById('editHospitalisation').value === 'true',
                    tuberculoses: document.getElementById('editTuberculose').value === 'true',
                    vit_seul: document.getElementById('editVitSeul').value === 'true',
                    etude_secondaire_ou_plus: document.getElementById('editEtudeSecondaire').value === 'true'
                };
                try {
                    const response = await fetch('/api/predictions', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    });
                    if (response.ok) {
                        closeModal();
                        loadPredictions();
                        loadStats();
                    }
                } catch (error) { console.error(error); }
            }

            function advancedExport() {
                const format = document.getElementById('exportFormat').value;
                const predictionClass = document.getElementById('exportClass').value;
                const startDate = document.getElementById('exportStartDate').value;
                const endDate = document.getElementById('exportEndDate').value;
                const limit = document.getElementById('exportLimit').value;
                let url = '/api/export/predictions?format=' + format + '&limit=' + limit;
                if (predictionClass) url += '&prediction_class=' + encodeURIComponent(predictionClass);
                if (startDate) url += '&start_date=' + startDate;
                if (endDate) url += '&end_date=' + endDate;
                window.location.href = url;
            }

            // ===== INIT =====
            loadPredictions();
            setTimeout(loadStats, 500);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ============================================================================
# FONCTIONS UTILITAIRES ET ENDPOINTS SHAP
# ============================================================================

def validate_temps_suivi(months: int) -> float:
    if months < 0:
        return 0.0
    return float(months)

@router.post("/viz/shap-explain", response_model=ShapExplanationResponse)
async def shap_explain_new_patient(
    patient: PatientInput,
    ml_service = Depends(get_ml_service),
    db: Session = Depends(get_db)
):
    """
    Calcule les valeurs SHAP pour un nouveau patient et retourne l'explication complète.
    """
    try:
        if ml_service.prediction_pipeline is None:
            raise HTTPException(status_code=503, detail="Modèle non chargé")
        
        # ====================================================================
        # 1. Récupérer les données du formulaire et convertir en PascalCase
        # ====================================================================
        patient_dict = patient.dict()
        
        input_to_model_mapping = {
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
        
        normalized_dict = {}
        for key, value in patient_dict.items():
            model_key = input_to_model_mapping.get(key, key)
            normalized_dict[model_key] = value
        
        patient_dict = normalized_dict
        
        # ====================================================================
        # 2. Valider le temps de suivi (déjà en mois)
        # ====================================================================
        temps_suivi_mois = validate_temps_suivi(patient_dict['temps_suivi'])
        patient_dict['temps_suivi'] = temps_suivi_mois
        
        # ====================================================================
        # 3. Prédiction avec le modèle
        # ====================================================================
        predicted_class, probabilities = ml_service.predict(patient_dict)
        confidence = max(probabilities.values())
        
        # ====================================================================
        # 4. Vérifier le seuil de confiance
        # ====================================================================
        confidence_alert = get_confidence_alert(confidence, predicted_class)
        
        # ====================================================================
        # 5. RÈGLE CLINIQUE : Détection des cas à très haut risque de décès
        # ====================================================================
        high_risk_death = (
            patient_dict['CD4_debut'] < 200 and
            patient_dict['Stade_avance'] and
            patient_dict['Hospitalisation']
        )
        
        clinical_alert = None
        
        if high_risk_death and predicted_class != 'Décédé':
            predicted_class = 'Décédé'
            if 'Décédé' in probabilities:
                probabilities['Décédé'] = max(probabilities['Décédé'], 0.75)
            total = sum(probabilities.values())
            probabilities = {k: v/total for k, v in probabilities.items()}
            confidence = probabilities.get('Décédé', 0.75)
            clinical_alert = "⚠️ CORRECTION CLINIQUE: Patient à très haut risque de décès (CD4<200, stade avancé, hospitalisation). La prédiction a été ajustée en conséquence."
        
        # ====================================================================
        # 5.5 Formater l'alerte de confiance
        # ====================================================================
        def format_confidence_alert(confidence_alert: dict, confidence: float) -> str:
            message = confidence_alert['message']
            if '(' in message and '%)' in message:
                import re
                message = re.sub(r'\([0-9,.]+%\)', f'({confidence:.1%})', message)
            return f"{confidence_alert['icon']} {message}"
        
        if confidence < MIN_CONFIDENCE_THRESHOLD:
            formatted_alert = format_confidence_alert(confidence_alert, confidence)
            if clinical_alert:
                clinical_alert = f"{formatted_alert}\n\n{clinical_alert}"
            else:
                clinical_alert = formatted_alert
        
        # ====================================================================
        # 6. Créer le dictionnaire dans le BON ORDRE
        # ====================================================================
        ordered_data = {}
        for col in ml_service.feature_names:
            value = patient_dict.get(col, 0)
            if col in ['Age_diagnostic', 'CD4_debut', 'Score_inf_opp', 'temps_suivi']:
                ordered_data[col] = float(value) if value is not None else 0.0
            else:
                ordered_data[col] = int(bool(value))

        # ====================================================================
        # 7. Créer DataFrame avec le bon ordre
        # ====================================================================
        df_patient = pd.DataFrame([ordered_data])[ml_service.feature_names]

        # ====================================================================
        # 8. Extraire le classifier du pipeline
        # ====================================================================
        if hasattr(ml_service.prediction_pipeline, 'named_steps'):
            classifier = ml_service.prediction_pipeline.named_steps.get('classifier')
            preprocessor = ml_service.prediction_pipeline.named_steps.get('preprocessor')
        else:
            classifier = ml_service.prediction_pipeline
            preprocessor = None
        
        # ====================================================================
        # 9. Appliquer le preprocessor si nécessaire
        # ====================================================================
        if preprocessor is not None:
            try:
                X_processed = preprocessor.transform(df_patient)
            except Exception as e:
                print(f"⚠️ Erreur preprocessor: {e}")
                X_processed = df_patient.values
        else:
            X_processed = df_patient.values
        
        # ====================================================================
        # 10. Calculer SHAP
        # ====================================================================
        explainer = shap.TreeExplainer(classifier)
        shap_values_all = explainer.shap_values(X_processed)
        
        # ====================================================================
        # 11. Définir les classes
        # ====================================================================
        class_names = ['Décédé', 'Perdu de Vue', 'Transféré', 'Vivant']
        pred_idx = class_names.index(predicted_class)
        
        # ====================================================================
        # 12. Extraire les SHAP values pour la classe PRÉDITE
        # ====================================================================
        if isinstance(shap_values_all, list):
            shap_values_raw = shap_values_all[pred_idx][0]
        elif len(shap_values_all.shape) == 3:
            shap_values_raw = shap_values_all[0, :, pred_idx]
        else:
            shap_values_raw = shap_values_all[0]
        
        shap_values_pred = shap_values_raw
        shap_values_for_death = shap_values_raw
        
        # ====================================================================
        # 13. Créer dictionnaire SHAP avec noms FRANÇAIS
        # ====================================================================
        shap_dict = {}
        for i, feature in enumerate(ml_service.feature_names):
            if i < len(shap_values_for_death):
                display_name = FEATURE_NAMES_FR.get(feature, feature.replace('_', ' ').title())
                shap_dict[display_name] = float(shap_values_for_death[i])
            else:
                display_name = FEATURE_NAMES_FR.get(feature, feature.replace('_', ' ').title())
                shap_dict[display_name] = 0.0
        
        # ====================================================================
        # 14. Seuils cliniques et qualification des variables
        # ====================================================================
        CLINICAL_THRESHOLDS = {
            'Age_diagnostic': {
                'high': ('Âge avancé (≥60 ans)', 60),
                'low': ('Âge jeune', None)
            },
            'Score_inf_opp': {
                'high': ('Score IO élevé (>3)', 3),
                'low': ('Score IO bas (≤3)', None)
            },
            'temps_suivi': {
                'long': ('Suivi prolongé (≥5 ans)', 60),
                'short': ('Suivi court (<5 ans)', None)
            }
        }

        def qualify_continuous_feature(model_key: str, value: float) -> str:
            if model_key == 'CD4_debut':
                if value < 200:
                    return 'CD4 très bas (<200)'
                elif value < 350:
                    return 'CD4 bas (200-350)'
                elif value < 500:
                    return 'CD4 modéré (350-500)'
                else:
                    return 'CD4 normal (>500)'
            if model_key == 'Age_diagnostic':
                if value >= 60:
                    return 'Âge avancé (≥60 ans)'
                else:
                    return 'Âge jeune'
            thresholds = CLINICAL_THRESHOLDS.get(model_key)
            if not thresholds:
                return None
            if model_key == 'temps_suivi':
                long_label, long_threshold = thresholds.get('long')
                short_label, _ = thresholds.get('short')
                if value >= long_threshold:
                    return long_label
                else:
                    return short_label
            if 'high' in thresholds:
                high_label, high_threshold = thresholds['high']
                if value > high_threshold:
                    return high_label
            if 'low' in thresholds:
                low_label, _ = thresholds['low']
                return low_label
            return None

        # ====================================================================
        # 15. Identifier facteurs de risque et protecteurs
        # ====================================================================
        risk_items = []
        protective_items = []

        CLASS_CONFIG = {
            "Vivant": {"shap_positive": "protective", "shap_negative": "risk"},
            "Décédé": {"shap_positive": "risk", "shap_negative": "protective"},
            "Perdu de Vue": {"shap_positive": "risk", "shap_negative": "protective"},
            "Transféré": {"shap_positive": "risk", "shap_negative": "protective"},
        }
        config = CLASS_CONFIG.get(predicted_class, {"shap_positive": "risk", "shap_negative": "protective"})

        BINARY_FEATURES = {'Non_observant', 'Stade_avance', 'Hospitalisation',
                           'Tuberculoses', 'Vit_seul', 'Etude_secondaire_ou_plus'}

        for display_name, shap_val in shap_dict.items():
            if abs(shap_val) <= 0.02:
                continue
            model_key = FEATURE_NAMES_EN.get(display_name, display_name)
            patient_value = ordered_data.get(model_key)

            label = None
            if model_key in CLINICAL_THRESHOLDS:
                if patient_value is not None:
                    label = qualify_continuous_feature(model_key, patient_value)
                if label is None:
                    label = f"{display_name} = {patient_value}"
            elif model_key in BINARY_FEATURES and patient_value is not None:
                if patient_value == 1:
                    label = f"Présence de {display_name}"
                else:
                    label = f"Absence de {display_name}"
            else:
                label = display_name

            if shap_val > 0:
                if config["shap_positive"] == "protective":
                    protective_items.append((shap_val, label))
                else:
                    risk_items.append((shap_val, label))
            else:
                if config["shap_negative"] == "protective":
                    protective_items.append((shap_val, label))
                else:
                    risk_items.append((shap_val, label))

        # ====================================================================
        # 16. Surcharges cliniques
        # ====================================================================
        CLINICAL_OVERRIDES_BY_CLASS = {
            "Vivant": {"Suivi court (<5 ans)": 'risk'},
            "Perdu de Vue": {"Suivi court (<5 ans)": 'risk', "Présence de Hospitalisation": 'risk'},
            "Décédé": {"Présence de Hospitalisation": 'risk', "Présence de Tuberculose": 'risk'},
            "Transféré": {}
        }
        GLOBAL_OVERRIDES = {
            'CD4 très bas (<200)': 'risk',
            'Score IO élevé (>3)': 'risk',
            'Âge avancé (≥60 ans)': 'risk'
        }
        class_overrides = CLINICAL_OVERRIDES_BY_CLASS.get(predicted_class, {})
        all_overrides = {**class_overrides, **GLOBAL_OVERRIDES}

        indices_a_supprimer = []
        for i, (shap_val, label) in enumerate(protective_items):
            if label in all_overrides:
                risk_items.append((shap_val, label))
                indices_a_supprimer.append(i)
        for i in reversed(indices_a_supprimer):
            protective_items.pop(i)

        risk_items.sort(key=lambda x: abs(x[0]), reverse=True)
        protective_items.sort(key=lambda x: abs(x[0]), reverse=True)

        risk_factors = [label for _, label in risk_items[:5]]
        protective_factors = [label for _, label in protective_items[:5]]

        # ====================================================================
        # 17. Interprétation clinique
        # ====================================================================
        cd4 = ordered_data.get('CD4_debut', 0)
        score_io = ordered_data.get('Score_inf_opp', 0)
        age = ordered_data.get('Age_diagnostic', 0)
        suivi = ordered_data.get('temps_suivi', 0)

        descriptive_phrases = []
        if cd4 < 200:
            descriptive_phrases.append(f"CD4 très bas ({cd4}) → risque immunodépression sévère")
        elif cd4 < 350:
            descriptive_phrases.append(f"CD4 bas ({cd4}) → risque modéré")
        elif cd4 >= 500:
            descriptive_phrases.append(f"CD4 normal (>500) → bon pronostic immunologique")
        else:
            descriptive_phrases.append(f"CD4 à {cd4} → niveau intermédiaire")

        if score_io > 3:
            descriptive_phrases.append(f"Score IO élevé ({score_io}) → risque d'infections opportunistes")
        elif score_io > 0:
            descriptive_phrases.append(f"Score IO modéré ({score_io}) → surveillance recommandée")
        else:
            descriptive_phrases.append("Score IO bas (≤3) → faible risque infectieux")

        if age >= 60:
            descriptive_phrases.append(f"Âge avancé ({age} ans) → facteur de risque")
        elif age <= 30:
            descriptive_phrases.append(f"Âge jeune ({age} ans) → facteur favorable")
        else:
            descriptive_phrases.append(f"Âge intermédiaire ({age} ans)")

        if suivi >= 60:
            descriptive_phrases.append(f"Suivi prolongé (≥5 ans) → suivi régulier, bonne observance présumée")
        elif suivi < 12:
            descriptive_phrases.append(f"Suivi très court (<1 an) → pronostic plus incertain")
        else:
            descriptive_phrases.append(f"Suivi de {suivi} mois → à consolider")

        clinical_summary = " | ".join(descriptive_phrases)

        if predicted_class == 'Vivant':
            main_factors = protective_factors[:3] if protective_factors else ['bon profil clinique']
            factor_type = "protecteurs"
        else:
            main_factors = risk_factors[:3] if risk_factors else ['éléments défavorables']
            factor_type = "de risque"

        force_urgence = False

        if predicted_class == 'Décédé':
            if high_risk_death:
                interpretation = (
                    f"🔴 URGENCE MÉDICALE : Risque TRÈS ÉLEVÉ de décès. "
                    f"Intervention immédiate requise. Facteurs critiques : CD4 < 200, stade avancé, hospitalisation."
                )
            else:
                interpretation = (
                    f"⚠️ Risque élevé de décès. Principaux facteurs {factor_type} : "
                    f"{', '.join(main_factors)}."
                )
            if any(label == 'Âge jeune' for _, label in protective_items):
                interpretation += " (Noter que l'âge jeune est ici un facteur modérateur, mais les autres facteurs de risque restent prépondérants.)"
        elif predicted_class == 'Perdu de Vue':
            interpretation = (
                f"⚠️ Risque de perte de vue. Renforcer l'observance thérapeutique "
                f"et le suivi psychosocial. Facteurs influents : {', '.join(main_factors)}."
            )
        elif predicted_class == 'Transféré':
            interpretation = (
                f"ℹ️ Patient susceptible d'être transféré. Coordonner avec le "
                f"centre de destination. Facteurs associés : {', '.join(main_factors)}."
            )
        else:  # Vivant
            critical_alerts = []
            if cd4 < 200:
                critical_alerts.append("CD4 < 200")
            if score_io > 3:
                critical_alerts.append("Score IO > 3")
            if age >= 60:
                critical_alerts.append("Âge ≥ 60 ans")
            if suivi < 12:
                critical_alerts.append("Suivi < 1 an")

            stade_avance = ordered_data.get('Stade_avance', 0)
            tuberculose = ordered_data.get('Tuberculoses', 0)
            if (cd4 < 200 and age >= 60 and (stade_avance == 1 or tuberculose == 1)):
                interpretation = (
                    f"⚠️⚠️⚠️ ALERTE CLINIQUE : Le modèle prédit 'Vivant', mais le patient présente "
                    f"un tableau très défavorable (CD4 < 200, âge ≥ 60, "
                    f"{'stade avancé' if stade_avance == 1 else 'tuberculose'}). "
                    f"Cette prédiction est en contradiction avec les critères cliniques de risque élevé. "
                    f"Une évaluation urgente par le clinicien est OBLIGATOIRE, indépendamment de la prédiction."
                )
                force_urgence = True
            else:
                if critical_alerts and confidence < 0.5:
                    interpretation = (
                        f"⚠️ Prédiction favorable **mais** avec des facteurs de risque majeurs : "
                        f"{', '.join(critical_alerts)}. La confiance est modérée ({confidence:.1%}), "
                        f"une évaluation clinique approfondie est recommandée."
                    )
                else:
                    interpretation = (
                        f"✅ Pronostic favorable. Les principaux facteurs {factor_type} sont : "
                        f"{', '.join(main_factors)}. "
                        f"Maintenir l'observance et le suivi régulier."
                    )

        interpretation += f"\n\n📊 Synthèse clinique : {clinical_summary}"

        if confidence < MIN_CONFIDENCE_THRESHOLD and confidence_alert:
            interpretation += f"\n\n⚠️ {confidence_alert['icon']} {confidence_alert['message']}"

        if predicted_class != 'Vivant':
            critical_alerts_autres = []
            if cd4 < 200:
                critical_alerts_autres.append("CD4 < 200")
            if score_io > 3:
                critical_alerts_autres.append("Score IO > 3")
            if age >= 60:
                critical_alerts_autres.append("Âge ≥ 60 ans")
            if suivi < 12:
                critical_alerts_autres.append("Suivi < 1 an")
            if critical_alerts_autres:
                interpretation += f"\n\n⚠️ Points d'attention : {', '.join(critical_alerts_autres)}. Une vigilance particulière est recommandée."

        if predicted_class == 'Décédé' or force_urgence:
            interpretation += "\n\n🔄 Recommandation : Évaluation urgente par le clinicien responsable."
        elif predicted_class == 'Perdu de Vue':
            interpretation += "\n\n🔄 Recommandation : Renforcer le contact téléphonique et les rappels de rendez-vous."
        elif predicted_class == 'Vivant':
            if (cd4 < 200 or score_io > 3 or age >= 60 or suivi < 12) and confidence < 0.5:
                interpretation += "\n\n🔄 Recommandation : Renforcer le suivi, évaluation clinique rapprochée malgré la prédiction favorable."
            else:
                interpretation += "\n\n🔄 Recommandation : Poursuivre le suivi standard, maintenir l'observance."
        else:
            interpretation += "\n\n🔄 Recommandation : Préparer la transition vers le nouveau centre."

        # ====================================================================
        # 18. Sauvegarder graphique Waterfall
        # ====================================================================
        waterfall_url = None
        try:
            expected_value = explainer.expected_value
            if isinstance(expected_value, list):
                if pred_idx < len(expected_value):
                    base_value = expected_value[pred_idx]
                else:
                    base_value = expected_value[0]
            else:
                base_value = expected_value
            
            explanation = shap.Explanation(
                values=shap_values_pred,
                base_values=base_value,
                data=df_patient.iloc[0].values,
                feature_names=ml_service.feature_names
            )
            
            fig, ax = plt.subplots(figsize=(12, 7))
            display_features = [FEATURE_NAMES_FR.get(f, f.replace('_', ' ').title()) 
                            for f in ml_service.feature_names]
            
            try:
                shap.plots.waterfall(explanation, show=False, max_display=10)
            except:
                values = explanation.values
                sorted_idx = np.argsort(np.abs(values))[::-1][:10]
                colors = ['#e74c3c' if values[i] > 0 else '#27ae60' for i in sorted_idx]
                bars = ax.barh(range(len(sorted_idx)), [values[i] for i in sorted_idx], color=colors)
                ax.set_yticks(range(len(sorted_idx)))
                ax.set_yticklabels([display_features[i] for i in sorted_idx])
                ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
                ax.set_xlabel('SHAP value (contribution à la prédiction)', fontsize=10)
                ax.set_title(f"SHAP Waterfall - Prédiction: {predicted_class}\nConfiance: {confidence:.1%}", 
                        fontweight='bold', fontsize=12)
                for i, (bar, idx) in enumerate(zip(bars, sorted_idx)):
                    ax.text(bar.get_width() + 0.01 * max(abs(values)), 
                        bar.get_y() + bar.get_height()/2,
                        f'{values[idx]:+.3f}', va='center', fontsize=9)
            
            plt.tight_layout()
            patient_hash = hashlib.md5(f"{time.time()}{patient.age_diagnostic}".encode()).hexdigest()[:8]
            filename = f"shap_waterfall_{patient_hash}.png"
            filepath = STATIC_DIR / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            if filepath.exists():
                waterfall_url = f"/static/plots/{filename}"
        except Exception as e:
            print(f"⚠️ Erreur création waterfall: {e}")
            waterfall_url = None

        # ====================================================================
        # 19. Enregistrer la prédiction en base de données
        # ====================================================================
        try:
            create_prediction_log(db, {
                'age_diagnostic': patient.age_diagnostic,
                'cd4_debut': patient.cd4_debut,
                'score_inf_opp': float(patient.score_inf_opp),
                'temps_suivi': patient.temps_suivi,
                'stade_avance': patient.stade_avance,
                'non_observant': patient.non_observant,
                'hospitalisation': patient.hospitalisation,
                'tuberculoses': patient.tuberculoses,
                'vit_seul': patient.vit_seul,
                'etude_secondaire_ou_plus': patient.etude_secondaire_ou_plus,
                'predicted_class': predicted_class,
                'confidence': confidence,
                'probabilities': probabilities,
                'risk_factors': risk_factors,
                'protective_factors': protective_factors,
                'clinical_alert': clinical_alert,
                'interpretation': interpretation,
                'source': 'frontend',
                'raw_payload': patient.dict()
            })
        except Exception as log_error:
            print(f"⚠️ Échec enregistrement DB: {log_error}")

        # ====================================================================
        # 20. Retourner la réponse
        # ====================================================================
        return ShapExplanationResponse(
            prediction=predicted_class,
            confidence=confidence,
            probabilities=probabilities,
            shap_values=shap_dict,
            risk_factors=risk_factors,
            protective_factors=protective_factors,
            interpretation=interpretation,
            clinical_alert=clinical_alert,
            waterfall_image_url=waterfall_url,
            confidence_level=confidence_alert['level']
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur interne: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


# ============================================================================
# ENDPOINTS COMPLÉMENTAIRES
# ============================================================================

@router.get("/shap-image/{file_hash}")
async def get_shap_image(file_hash: str):
    """Récupère l'image SHAP générée"""
    file_path = STATIC_DIR / f"shap_waterfall_{file_hash}.png"
    if file_path.exists():
        return FileResponse(file_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Image SHAP non trouvée")

@router.delete("/viz/cleanup")
async def cleanup_old_plots(hours: int = 24):
    """Nettoie les anciens graphiques SHAP"""
    import time
    deleted = 0
    current_time = time.time()
    for filepath in STATIC_DIR.glob("shap_waterfall_*.png"):
        if current_time - filepath.stat().st_mtime > hours * 3600:
            filepath.unlink()
            deleted += 1
    return {"message": f"Nettoyé {deleted} fichiers plus vieux que {hours} heures"}