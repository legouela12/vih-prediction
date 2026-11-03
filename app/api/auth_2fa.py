"""
Endpoints pour l'authentification à deux facteurs
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging

from app.auth.jwt_handler import get_current_user

router = APIRouter()

logger = logging.getLogger(__name__)


# ============================================================================
# MODÈLES
# ============================================================================

class TwoFactorSetupRequest(BaseModel):
    username: str


class TwoFactorVerifyRequest(BaseModel):
    username: str
    code: str


class TwoFactorEnableRequest(BaseModel):
    username: str
    code: str


class TwoFactorPhoneRequest(BaseModel):
    username: str
    phone_number: str


class TwoFactorSMSCodeRequest(BaseModel):
    username: str
    code: str


# ============================================================================
# BASE DE DONNÉES 2FA (Temporaire)
# ============================================================================

TWO_FA_SECRETS = {}


def is_2fa_enabled(username: str) -> bool:
    user_data = TWO_FA_SECRETS.get(username)
    if user_data:
        return user_data.get("enabled", False)
    return False


def get_2fa_secret(username: str):
    user_data = TWO_FA_SECRETS.get(username)
    if user_data:
        return user_data.get("secret")
    return None


def verify_2fa_code(username: str, code: str) -> bool:
    import pyotp
    
    secret = get_2fa_secret(username)
    if not secret:
        return False
    
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def verify_temp_2fa_code(username: str, code: str) -> bool:
    user_data = TWO_FA_SECRETS.get(username)
    if not user_data:
        return False
    
    temp_code = user_data.get("temp_code")
    if not temp_code:
        return False
    
    return temp_code == code


DEMO_2FA_CODES = {
    "admin": "123456",
    "doctor": "654321",
    "nurse": "987654"
}


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/2fa/setup/{username}")
async def setup_2fa(username: str):
    import pyotp
    import qrcode
    import io
    import base64
    
    from app.auth.jwt_handler import USERS_DB
    if username not in USERS_DB:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    secret = pyotp.random_base32()
    TWO_FA_SECRETS[username] = {
        "secret": secret,
        "enabled": False,
        "created_at": __import__("datetime").datetime.now().isoformat()
    }
    
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(username, issuer_name="VIH Prediction")
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    qr_base64 = f"data:image/png;base64,{img_str}"
    
    return {
        "success": True,
        "secret": secret,
        "qr_code": qr_base64,
        "message": "Scannez le QR code avec Google Authenticator"
    }


@router.post("/2fa/enable")
async def enable_2fa_endpoint(request: TwoFactorEnableRequest):
    if not verify_2fa_code(request.username, request.code):
        if request.username not in DEMO_2FA_CODES or DEMO_2FA_CODES[request.username] != request.code:
            raise HTTPException(
                status_code=401, 
                detail="Code 2FA invalide"
            )
    
    if request.username in TWO_FA_SECRETS:
        TWO_FA_SECRETS[request.username]["enabled"] = True
        return {
            "success": True,
            "message": "2FA activé avec succès"
        }
    
    raise HTTPException(
        status_code=400, 
        detail="Erreur lors de l'activation du 2FA"
    )


@router.post("/2fa/disable")
async def disable_2fa_endpoint(
    username: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Désactive le 2FA pour un utilisateur
    Nécessite une authentification (token JWT)
    """
    # Vérifier que l'utilisateur existe
    from app.auth.jwt_handler import USERS_DB
    if username not in USERS_DB:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur non trouvé"
        )
    
    # Vérifier les droits : admin ou l'utilisateur lui-même
    if current_user["username"] != username and current_user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas les droits pour désactiver le 2FA"
        )
    
    # Vérifier que le 2FA est activé
    if username not in TWO_FA_SECRETS:
        raise HTTPException(
            status_code=400,
            detail="Le 2FA n'est pas configuré pour cet utilisateur"
        )
    
    # Désactiver le 2FA
    TWO_FA_SECRETS[username]["enabled"] = False
    return {
        "success": True,
        "message": "2FA désactivé avec succès"
    }


@router.post("/2fa/reset/{username}")
async def reset_2fa(username: str):
    """
    🔓 RÉINITIALISATION D'URGENCE - UNIQUEMENT POUR LE DÉVELOPPEMENT
    Réinitialise le 2FA pour un utilisateur (sans authentification)
    """
    # ⚠️ À SUPPRIMER EN PRODUCTION !
    if username in TWO_FA_SECRETS:
        TWO_FA_SECRETS[username]["enabled"] = False
        return {
            "success": True,
            "message": f"2FA réinitialisé pour {username}"
        }
    raise HTTPException(
        status_code=404,
        detail="Utilisateur non trouvé"
    )


@router.get("/2fa/status/{username}")
async def get_2fa_status(username: str):
    enabled = is_2fa_enabled(username)
    return {
        "username": username,
        "two_factor_enabled": enabled
    }


@router.post("/2fa/verify")
async def verify_2fa(request: TwoFactorVerifyRequest):
    if not is_2fa_enabled(request.username):
        return {
            "success": True,
            "message": "2FA non activé"
        }
    
    if verify_2fa_code(request.username, request.code):
        return {
            "success": True,
            "message": "Code 2FA valide"
        }
    elif verify_temp_2fa_code(request.username, request.code):
        return {
            "success": True,
            "message": "Code 2FA valide (SMS)"
        }
    elif request.username in DEMO_2FA_CODES and DEMO_2FA_CODES[request.username] == request.code:
        return {
            "success": True,
            "message": "Code 2FA valide (démonstration)"
        }
    else:
        raise HTTPException(
            status_code=401,
            detail="Code 2FA invalide"
        )


@router.post("/2fa/sms/send")
async def send_2fa_sms(request: TwoFactorPhoneRequest):
    if not is_2fa_enabled(request.username):
        raise HTTPException(
            status_code=400,
            detail="Le 2FA n'est pas activé pour cet utilisateur"
        )
    
    import random
    code = str(random.randint(100000, 999999))
    
    if request.username in TWO_FA_SECRETS:
        TWO_FA_SECRETS[request.username]["temp_code"] = code
    
    return {
        "success": True,
        "message": "Code 2FA envoyé par SMS",
        "demo_code": code
    }


@router.post("/2fa/sms/verify")
async def verify_2fa_sms(request: TwoFactorSMSCodeRequest):
    if verify_temp_2fa_code(request.username, request.code):
        return {
            "success": True,
            "message": "Code SMS valide"
        }
    else:
        raise HTTPException(
            status_code=401,
            detail="Code SMS invalide ou expiré"
        )


# ============================================================================
# PAGE DE CONFIGURATION 2FA (Interface HTML) - VERSION CORRIGÉE
# ============================================================================

@router.get("/2fa/setup-page", response_class=HTMLResponse)
async def two_factor_setup_page():
    """Page de configuration du 2FA"""
    
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Configuration 2FA - VIH Prediction</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #eef2f5; padding: 20px; min-height: 100vh; display: flex; justify-content: center; align-items: center; }
        .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        h1 { color: #1f6392; margin-bottom: 10px; }
        .subtitle { color: #64748b; margin-bottom: 30px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: 500; margin-bottom: 5px; color: #2c3e50; }
        input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 1rem; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: 0.2s; }
        .btn-primary { background: #1f6392; color: white; }
        .btn-primary:hover { background: #134b6f; }
        .btn-success { background: #27ae60; color: white; }
        .btn-success:hover { background: #219a52; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-danger:hover { background: #c0392b; }
        .btn-warning { background: #f39c12; color: white; }
        .btn-warning:hover { background: #e67e22; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .qr-code { text-align: center; margin: 20px 0; }
        .qr-code img { max-width: 200px; border: 2px solid #e9edf2; border-radius: 12px; }
        .secret { background: #f8fafc; padding: 10px; border-radius: 8px; font-family: monospace; word-break: break-all; margin: 10px 0; border: 1px solid #e9edf2; }
        .alert { padding: 12px; border-radius: 8px; margin-bottom: 15px; display: none; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; display: block; }
        .alert-danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; display: block; }
        .alert-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; display: block; }
        .demo-codes { margin-top: 20px; padding: 15px; background: #f8fafc; border-radius: 8px; border: 1px solid #e9edf2; }
        .demo-codes code { background: white; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
        .steps { margin: 20px 0; padding: 15px; background: #f0f7ff; border-radius: 8px; border-left: 4px solid #1f6392; }
        .steps ol { padding-left: 20px; }
        .steps li { margin: 8px 0; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; }
        .divider { margin: 30px 0; border: none; border-top: 1px solid #e9edf2; }
    </style>
</head>
<body>
    <div class="container">
        <h1><i class="fas fa-shield-alt" style="color: #1f6392;"></i> Authentification 2FA</h1>
        <p class="subtitle">Sécurisez votre compte avec l'authentification à deux facteurs</p>
        
        <div id="alert" class="alert"></div>
        
        <div class="steps">
            <h4>📋 Étapes de configuration :</h4>
            <ol>
                <li>Entrez votre nom d'utilisateur</li>
                <li>Générez un QR code</li>
                <li>Scannez-le avec Google Authenticator</li>
                <li>Entrez le code 6 chiffres</li>
                <li>Activez le 2FA</li>
            </ol>
        </div>
        
        <div class="form-group">
            <label><i class="fas fa-user"></i> Nom d'utilisateur</label>
            <input type="text" id="username" placeholder="admin, doctor ou nurse" value="admin">
        </div>
        
        <div class="btn-group">
            <button class="btn btn-primary" id="btnSetup">
                <i class="fas fa-qrcode"></i> Générer QR Code
            </button>
        </div>
        
        <div id="qrSection" style="display: none; margin-top: 20px;">
            <h3><i class="fas fa-qrcode"></i> Scannez ce QR Code</h3>
            <div class="qr-code" id="qrCodeContainer"></div>
            <p style="text-align: center; font-size: 0.9rem; color: #64748b;">
                Ou entrez manuellement cette clé secrète :
            </p>
            <div class="secret" id="secretContainer">-</div>
            
            <div class="form-group">
                <label><i class="fas fa-key"></i> Code 6 chiffres</label>
                <input type="text" id="verifyCode" placeholder="000000" maxlength="6" style="text-align: center; font-size: 1.2rem; letter-spacing: 4px;">
            </div>
            
            <button class="btn btn-success" id="btnEnable" style="width: 100%; margin-top: 10px;">
                <i class="fas fa-check"></i> Activer 2FA
            </button>
        </div>
        
        <hr class="divider">
        
        <div class="btn-group">
            <button class="btn btn-danger" id="btnDisable">
                <i class="fas fa-times"></i> Désactiver 2FA
            </button>
            <button class="btn btn-warning" id="btnStatus">
                <i class="fas fa-info-circle"></i> Vérifier statut
            </button>
        </div>
        
        <div class="demo-codes">
            <h4><i class="fas fa-info-circle"></i> Codes de démonstration :</h4>
            <p><code>admin</code> → <strong>123456</strong></p>
            <p><code>doctor</code> → <strong>654321</strong></p>
            <p><code>nurse</code> → <strong>987654</strong></p>
            <p style="font-size: 0.75rem; color: #94a3b8; margin-top: 8px;">
                ⚠️ Utilisez ces codes pour tester sans Google Authenticator
            </p>
        </div>
    </div>
    
    <script>
    var currentUsername = '';
    
    function showAlert(message, type) {
        var alertEl = document.getElementById('alert');
        alertEl.className = 'alert alert-' + type;
        alertEl.innerHTML = message;
        alertEl.style.display = 'block';
        setTimeout(function() {
            alertEl.style.display = 'none';
        }, 5000);
    }
    
    document.getElementById('btnSetup').addEventListener('click', function() {
        var username = document.getElementById('username').value.trim();
        if (!username) {
            showAlert("Veuillez entrer un nom d'utilisateur", 'danger');
            return;
        }
        currentUsername = username;
        
        var btn = this;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Chargement...';
        
        fetch('/api/auth/2fa/setup/' + username)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    document.getElementById('secretContainer').textContent = data.secret;
                    document.getElementById('qrCodeContainer').innerHTML = 
                        '<img src="' + data.qr_code + '" alt="QR Code" style="max-width:200px;">';
                    document.getElementById('qrSection').style.display = 'block';
                    showAlert('✅ QR Code généré avec succès !', 'success');
                } else {
                    showAlert(data.detail || 'Erreur lors de la génération du QR Code', 'danger');
                }
            })
            .catch(function() {
                showAlert('❌ Erreur de connexion au serveur', 'danger');
            })
            .finally(function() {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-qrcode"></i> Générer QR Code';
            });
    });
    
    document.getElementById('btnEnable').addEventListener('click', function() {
        var code = document.getElementById('verifyCode').value.trim();
        if (!code || code.length !== 6) {
            showAlert('Veuillez entrer un code 2FA valide (6 chiffres)', 'danger');
            return;
        }
        
        var btn = this;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Activation...';
        
        fetch('/api/auth/2fa/enable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: currentUsername, code: code })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                showAlert('✅ 2FA activé avec succès !', 'success');
                document.getElementById('qrSection').style.display = 'none';
            } else {
                showAlert(data.detail || 'Code invalide', 'danger');
            }
        })
        .catch(function() {
            showAlert('❌ Erreur de connexion au serveur', 'danger');
        })
        .finally(function() {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-check"></i> Activer 2FA';
        });
    });
    
    document.getElementById('btnDisable').addEventListener('click', function() {
        var username = document.getElementById('username').value.trim();
        if (!username) {
            showAlert("Veuillez entrer un nom d'utilisateur", 'danger');
            return;
        }
        
        if (!confirm('Voulez-vous vraiment désactiver le 2FA pour ' + username + ' ?')) {
            return;
        }
        
        // Récupérer le token depuis localStorage
        var token = localStorage.getItem('access_token');
        if (!token) {
            showAlert('❌ Vous devez être connecté pour désactiver le 2FA. Veuillez vous connecter d\'abord.', 'danger');
            return;
        }
        
        fetch('/api/auth/2fa/disable?username=' + username, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            }
        })
        .then(function(response) { 
            if (!response.ok) {
                return response.json().then(function(data) {
                    throw new Error(data.detail || 'Erreur ' + response.status);
                });
            }
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                showAlert('✅ 2FA désactivé avec succès', 'success');
                document.getElementById('qrSection').style.display = 'none';
            } else {
                showAlert(data.detail || 'Erreur lors de la désactivation', 'danger');
            }
        })
        .catch(function(error) {
            showAlert('❌ ' + error.message, 'danger');
        });
    });
    
    document.getElementById('btnStatus').addEventListener('click', function() {
        var username = document.getElementById('username').value.trim();
        if (!username) {
            showAlert("Veuillez entrer un nom d'utilisateur", 'danger');
            return;
        }
        
        fetch('/api/auth/2fa/status/' + username)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.two_factor_enabled) {
                    showAlert('✅ Le 2FA est ACTIVÉ pour ' + username, 'success');
                } else {
                    showAlert('⚠️ Le 2FA est DÉSACTIVÉ pour ' + username, 'info');
                }
            })
            .catch(function() {
                showAlert('❌ Erreur de connexion au serveur', 'danger');
            });
    });
    </script>
</body>
</html>
    """
    
    return HTMLResponse(content=html_content)