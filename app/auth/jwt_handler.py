"""
Gestion de l'authentification JWT - Version sans bcrypt
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import hashlib
import os
from dotenv import load_dotenv
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

# Configuration JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ma_super_cle_secrete_pour_jwt_2024_change_me")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash un mot de passe avec SHA-256 (simple mais efficace pour la démo)"""
    return hashlib.sha256(f"vih_salt_2024_{password}".encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe"""
    return hash_password(plain_password) == hashed_password


# Base de données utilisateurs
USERS_DB = {
    "admin": {
        "username": "admin",
        "password": hash_password("admin123"),
        "role": "admin",
        "email": "admin@hopital.fr",
        "full_name": "Administrateur"
    },
    "doctor": {
        "username": "doctor",
        "password": hash_password("doctor123"),
        "role": "doctor",
        "email": "medecin@hopital.fr",
        "full_name": "Dr Martin"
    },
    "nurse": {
        "username": "nurse",
        "password": hash_password("nurse123"),
        "role": "nurse",
        "email": "infirmier@hopital.fr",
        "full_name": "Infirmier Dupont"
    }
}


def get_user(username: str):
    return USERS_DB.get(username)


def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user["password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = get_user(username)
    if user is None:
        raise credentials_exception
    return user


def require_role(allowed_roles: list):
    async def role_checker(user = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' non autorisé. Requis: {allowed_roles}"
            )
        return user
    return role_checker