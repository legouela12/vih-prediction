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

    def check_browser_session(self, cookie_header: str) -> bool:
        """Validate a browser's OpenMRS session without using service credentials."""
        try:
            response = requests.get(
                f"{self.base_url}/session",
                headers={"Cookie": cookie_header, "Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return bool(response.json().get("authenticated", False))
        except (requests.RequestException, ValueError):
            return False

    def get_patient(self, patient_uuid: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations démographiques d'un patient"""
        url = f"{self.base_url}/patient/{patient_uuid}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            return None

    def get_observations(
        self,
        patient_uuid: str,
        concept_uuid: str,
        order: str = "desc",
        limit: int = 100,
    ) -> Optional[List[Dict]]:
        """Fetch observations for a patient and concept in date order."""
        url = f"{self.base_url}/obs"
        try:
            resp = self.session.get(
                url,
                params={
                    "patient": patient_uuid,
                    "concept": concept_uuid,
                    # Some OpenMRS REST versions serialize `value` incorrectly
                    # when `orderBy=obsDatetime` is used. Sort the returned
                    # observations locally instead.
                    "limit": max(limit, 100),
                    "v": "full",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get('results', [])
            results.sort(
                key=lambda obs: obs.get("obsDatetime") or "",
                reverse=order.lower() != "asc",
            )
            return results[:limit]
        except (requests.RequestException, ValueError):
            return None

    def get_encounters(self, patient_uuid: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch a patient's latest encounters, including diagnoses."""
        try:
            response = self.session.get(
                f"{self.base_url}/encounter",
                params={
                    "patient": patient_uuid,
                    "orderBy": "encounterDatetime desc",
                    "limit": 100,
                    "v": "full",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except (requests.RequestException, ValueError):
            return None

    def get_encounter(self, encounter_uuid: str) -> Optional[Dict[str, Any]]:
        """Fetch one encounter with its form, observations, patient and location."""
        try:
            response = self.session.get(
                f"{self.base_url}/encounter/{encounter_uuid}",
                params={"v": "full"},
                timeout=self.timeout,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def get_patient_diagnosis_uuids(self, patient_uuid: str) -> Optional[set]:
        """Collect coded diagnosis concept UUIDs from the patient's encounters."""
        encounters = self.get_encounters(patient_uuid)
        if encounters is None:
            return None

        diagnosis_uuids = set()
        for encounter in encounters:
            for diagnosis in encounter.get("diagnoses", []) or []:
                candidates = [diagnosis]
                while candidates:
                    item = candidates.pop()
                    if not isinstance(item, dict):
                        continue
                    for key, value in item.items():
                        if key in {"coded", "concept"} and isinstance(value, dict):
                            uuid = value.get("uuid")
                            if uuid:
                                diagnosis_uuids.add(uuid)
                        elif key in {"diagnosis", "coded", "concept"} and isinstance(value, dict):
                            candidates.append(value)
        return diagnosis_uuids

    def has_encounter_type(
        self, patient_uuid: str, encounter_type_uuid: str
    ) -> Optional[bool]:
        """Return whether the patient has a matching encounter type."""
        try:
            response = self.session.get(
                f"{self.base_url}/encounter",
                params={
                    "patient": patient_uuid,
                    "encounterType": encounter_type_uuid,
                    "limit": 1,
                    "v": "ref",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return bool(response.json().get("results", []))
        except (requests.RequestException, ValueError):
            return None

    def create_observation(
        self,
        patient_uuid: str,
        concept_uuid: str,
        value: str,
        obs_datetime: str,
        encounter_uuid: Optional[str] = None,
        location_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an informational text observation linked to its visit encounter."""
        payload = {
            "person": patient_uuid,
            "concept": concept_uuid,
            "value": value,
            "obsDatetime": obs_datetime,
        }
        if encounter_uuid:
            payload["encounter"] = encounter_uuid
        if location_uuid:
            payload["location"] = location_uuid
        response = self.session.post(
            f"{self.base_url}/obs",
            json=payload,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_latest_obs_value(self, patient_uuid: str, concept_uuid: str) -> Optional[float]:
        """Récupère la dernière valeur d'une observation (ex: dernier CD4)"""
        obs_list = self.get_observations(patient_uuid, concept_uuid)
        if obs_list:
            latest = obs_list[0]
            value = latest.get('value')
            if isinstance(value, (int, float)):
                return float(value)
        return None
