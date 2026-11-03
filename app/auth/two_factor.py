"""
Authentification à deux facteurs (2FA)
"""
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict
import os
from dotenv import load_dotenv

load_dotenv()

# Base de données des secrets 2FA (à remplacer par une vraie BD)
TWO_FA_SECRETS: Dict[str, dict] = {}

# Configuration
TWO_FA_ISSUER = "VIH Prediction"
TWO_FA_WINDOW = 1  # Tolérance de 1 intervalle


def generate_2fa_secret(username: str) -> str:
    """
    Génère un secret 2FA pour un utilisateur
    """
    secret = pyotp.random_base32()
    TWO_FA_SECRETS[username] = {
        "secret": secret,
        "enabled": False,
        "created_at": datetime.now().isoformat()
    }
    return secret


def get_2fa_secret(username: str) -> Optional[str]:
    """
    Récupère le secret 2FA d'un utilisateur
    """
    user_data = TWO_FA_SECRETS.get(username)
    if user_data:
        return user_data["secret"]
    return None


def enable_2fa(username: str) -> bool:
    """
    Active le 2FA pour un utilisateur
    """
    if username in TWO_FA_SECRETS:
        TWO_FA_SECRETS[username]["enabled"] = True
        return True
    return False


def disable_2fa(username: str) -> bool:
    """
    Désactive le 2FA pour un utilisateur
    """
    if username in TWO_FA_SECRETS:
        TWO_FA_SECRETS[username]["enabled"] = False
        return True
    return False


def is_2fa_enabled(username: str) -> bool:
    """
    Vérifie si le 2FA est activé pour un utilisateur
    """
    user_data = TWO_FA_SECRETS.get(username)
    if user_data:
        return user_data.get("enabled", False)
    return False


def verify_2fa_code(username: str, code: str) -> bool:
    """
    Vérifie le code 2FA
    """
    secret = get_2fa_secret(username)
    if not secret:
        return False
    
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=TWO_FA_WINDOW)


def generate_qr_code(username: str) -> Optional[str]:
    """
    Génère un QR code pour l'application Google Authenticator
    """
    secret = get_2fa_secret(username)
    if not secret:
        return None
    
    # Créer l'URI pour Google Authenticator
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(username, issuer_name=TWO_FA_ISSUER)
    
    # Générer le QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convertir en base64 pour l'affichage
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


# Pour la démonstration : codes 2FA temporaires
# Dans une vraie application, utiliser SMS ou email
DEMO_2FA_CODES = {
    "admin": "123456",
    "doctor": "654321",
    "nurse": "987654"
}


def send_2fa_code_sms(username: str, phone_number: str) -> str:
    """
    Envoie un code 2FA par SMS (simulation)
    """
    # Simuler l'envoi d'un SMS
    import random
    code = str(random.randint(100000, 999999))
    
    # Stocker le code pour vérification (expire après 5 min)
    TWO_FA_SECRETS[username]["temp_code"] = code
    TWO_FA_SECRETS[username]["temp_code_expires"] = (
        datetime.now() + timedelta(minutes=5)
    ).isoformat()
    
    print(f"📱 SMS envoyé à {phone_number}: {code}")
    return code


def verify_temp_2fa_code(username: str, code: str) -> bool:
    """
    Vérifie le code 2FA temporaire (SMS/Email)
    """
    user_data = TWO_FA_SECRETS.get(username)
    if not user_data:
        return False
    
    temp_code = user_data.get("temp_code")
    expires = user_data.get("temp_code_expires")
    
    if not temp_code or not expires:
        return False
    
    # Vérifier si le code a expiré
    expires_dt = datetime.fromisoformat(expires)
    if datetime.now() > expires_dt:
        return False
    
    return temp_code == code