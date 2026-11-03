import requests
from requests.auth import HTTPBasicAuth
from typing import Optional, Dict, Any, List

class OpenMRSClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.auth = HTTPBasicAuth(username, password)
        self.session = requests.Session()
        self.session.auth = self.auth

    def check_connection(self) -> Dict[str, Any]:
        """Check that OpenMRS is reachable and the configured credentials work."""
        try:
            response = self.session.get(f"{self.base_url}/session", timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return {
                "reachable": True,
                "authenticated": bool(data.get("authenticated", False)),
                "user": data.get("user", {}).get("username"),
            }
        except requests.RequestException as exc:
            return {
                "reachable": False,
                "authenticated": False,
                "error": str(exc),
            }
        except (TypeError, ValueError) as exc:
            return {
                "reachable": True,
                "authenticated": False,
                "error": f"Réponse OpenMRS invalide: {exc}",
            }

    def get_patient(self, patient_uuid: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations démographiques d'un patient"""
        url = f"{self.base_url}/patient/{patient_uuid}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"❌ Erreur patient {patient_uuid}: {e}")
            return None

    def get_observations(self, patient_uuid: str, concept_uuid: str) -> Optional[List[Dict]]:
        """Récupère toutes les observations pour un concept donné"""
        url = f"{self.base_url}/obs?patient={patient_uuid}&concept={concept_uuid}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data.get('results', [])
        except Exception as e:
            print(f"❌ Erreur obs {patient_uuid}/{concept_uuid}: {e}")
            return None

    def get_latest_obs_value(self, patient_uuid: str, concept_uuid: str) -> Optional[float]:
        """Récupère la dernière valeur d'une observation (ex: dernier CD4)"""
        obs_list = self.get_observations(patient_uuid, concept_uuid)
        if obs_list:
            # Trie par date pour prendre la plus récente
            sorted_obs = sorted(obs_list, key=lambda x: x.get('obsDatetime', ''), reverse=True)
            latest = sorted_obs[0]
            value = latest.get('value')
            if isinstance(value, (int, float)):
                return float(value)
        return None