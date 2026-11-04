# Kit de migration OpenMRS

Ce kit transporte la configuration Docker OpenMRS actuelle et l’extension O3 VIH.
Les images Docker sont épinglées aux empreintes actuellement utilisées. Les
montages de l’extension sont relatifs au dossier du kit et ne dépendent donc pas
des chemins absolus de ce PC.

## Contenu

- `compose.yaml` : gateway, frontend, backend et MariaDB avec les versions actuelles.
- `openmrs-extension/` : fichiers compilés de l’extension VIH actuellement chargée.
- `backup/openmrs.sql.gz` : base OpenMRS, patients, observations, formulaires et métadonnées.
- `backup/openmrs-data.tar.gz` : fichiers OpenMRS, modules, configuration et images de personnes.
- `.env` : mots de passe techniques MariaDB générés pour la restauration. Ce fichier est privé et ignoré par Git.

Les sauvegardes contiennent des données de santé sensibles. Elles et le fichier
`.env` sont ignorés par Git. Le paquet de transfert fourni est chiffré; la clé
doit être transmise séparément, par un canal sûr.

## Sur l’autre PC

1. Transférer `transfer/openmrs-migration-kit.tar.gz.enc` et la clé par deux
   canaux séparés. Les instructions de déchiffrement sont dans
   `transfer/README-transfer.txt`.
2. Installer Docker Engine avec le greffon Docker Compose.
3. Depuis le dossier extrait `migration-kit`, exécuter `./restore-openmrs.sh`.
4. Ouvrir `http://127.0.0.1:8080/openmrs` (ou le port défini dans `.env`).

Le script crée les volumes `vih-openmrs-db` et `vih-openmrs-data`, restaure la
base, restaure les fichiers, puis démarre les quatre services. Il refuse
d’importer la sauvegarde si la base cible contient déjà des tables OpenMRS ou
si le volume de fichiers n’est pas vide. Ne lancez pas `docker compose down -v`
après la restauration : cette commande supprimerait les données.

## Recréer la sauvegarde sur ce PC

Depuis le dépôt, exécuter `./migration-kit/backup-current-openmrs.sh`. Le script
sauvegarde les conteneurs actifs `e_db_1` et `e_backend_1`; les noms peuvent être
changés avec `OPENMRS_DB_CONTAINER` et `OPENMRS_BACKEND_CONTAINER`. Le volume
`e_openmrs-data` peut être sélectionné avec `OPENMRS_DATA_VOLUME`. La base est
exportée par `mariadb-dump` en transaction cohérente; les fichiers OpenMRS sont
archivés en lecture seule depuis leur volume Docker.

Cette sauvegarde ne contient pas le service FastAPI, le modèle d’IA ni la base
SQLite de l’application. Elle porte sur OpenMRS et son extension O3.
