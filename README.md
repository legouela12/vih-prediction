
## Intégration OpenMRS → prédiction → dossier patient

Le backend expose `POST /api/openmrs/patient/{patient_uuid}/predict`. Il lit les
données OpenMRS, calcule les 10 variables selon les règles du notebook, calcule
la prédiction, puis enregistre un texte d'aide à la décision dans une observation
du patient. L'ancienne route `GET /api/predict-from-openmrs/{patient_uuid}`
reste disponible en lecture seule pour compatibilité.

### Configuration requise

1. Copier `.env.example` vers `.env` et renseigner l'URL REST, un compte de
   service OpenMRS dédié et son mot de passe. Pour un backend lancé avec
   `python run_api.py` sur le même PC que notre installation locale, l'URL est
   `http://127.0.0.1:8080/openmrs/ws/rest/v1`. Ne pas utiliser le compte admin.
   Générer aussi `OPENMRS_INTEGRATION_TOKEN` (par exemple avec
   `openssl rand -hex 32`) pour les appels serveur-à-serveur. L'extension O3
   utilise la session OpenMRS de l'utilisateur et ne place aucun jeton secret
   dans le navigateur. Le compte indiqué dans `.env` est celui configuré sur
   cette machine; pour un usage durable, créer un compte de service avec les
   droits REST minimaux.
2. Le dictionnaire local contient maintenant quatre questions booléennes pour
   les entrées dérivées (stade avancé, non-observance, `Vit_seul`, études
   secondaires ou plus) et un concept texte de résultat IA. Leurs UUID sont
   renseignés dans le `.env` local. Pour une autre instance, importer ces
   concepts et reporter les UUID de destination.
3. Le connecteur utilise les concepts CIEL `160554AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`
   (date de diagnostic VIH), `5497AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` (CD4 count),
   et les diagnostics CIEL des six infections opportunistes définies dans le code.
   Il calcule l'âge au diagnostic à partir de la date de naissance, le suivi à
   partir de la date de diagnostic et du dernier contact (ou date de décès), et
   le score d'infections par somme des six diagnostics.
4. Le formulaire clinique O3 doit inclure les quatre questions booléennes afin
   que les observations puissent être saisies pour chaque patient. Elles signifient:
   OMS III/IV; non-observant; célibataire/veuf/veuve (variable `Vit_seul` du
   notebook); secondaire/universitaire. L'hospitalisation est déduite d'un
   encounter de type Admission.
5. Redémarrer FastAPI. L'API renvoie `422` si une donnée indispensable (date de
   naissance, date du diagnostic VIH, CD4 initial ou date de contact) manque.
   Les variables booléennes sans observation valent 0, comme dans la préparation
   des données du notebook.

Exemple (UUID de patient de démonstration uniquement):

```bash
curl -X POST \
  -H 'Authorization: Bearer <OPENMRS_INTEGRATION_TOKEN>' \
  http://127.0.0.1:8000/api/openmrs/patient/<UUID_PATIENT>/predict
```

Le compte de service doit pouvoir lire les patients, observations, encounters et
diagnostics, et créer une observation. L'API REST OpenMRS utilise
`POST /ws/rest/v1/obs` pour créer une ressource; les opérations REST requièrent
une authentification. La prédiction reste une aide à la décision et ne doit pas
être enregistrée comme diagnostic VIH ni comme résultat de laboratoire.

Le schéma O3 prêt à importer est fourni dans
`openmrs-esm-vih-prediction-app/vih_prediction_form.json`. Il contient les
questions cliniques et l'action `VihPredictionSubmissionAction`.

L'extension O3 se trouve dans `openmrs-esm-vih-prediction-app/`. Elle est
chargée avec le bandeau patient via `patient-banner-tags-slot`; après la
sauvegarde réussie du formulaire, elle envoie l'UUID de la rencontre à
`POST /openmrs/api/openmrs/encounter/{encounter_uuid}/predict`. FastAPI valide
la session OpenMRS de l'utilisateur, calcule la prédiction et enregistre le
texte de résultat dans la rencontre. Le navigateur doit pouvoir joindre
FastAPI sur le port 8000; les origines autorisées par défaut sont
`http://localhost:8080` et `http://127.0.0.1:8080`.

Le notebook d'entraînement calcule `temps_suivi` en mois (`jours / 30,44`);
le connecteur applique la même conversion.
