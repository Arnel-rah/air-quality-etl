#  Spécifications Techniques & Architecture — Pipeline Data ETL

## 1. Data Lineage & Design Global

Le pipeline récupère les données brutes de l'API stockées sous leur forme brute pour assurer un suivi complet. Cela garantit qu'aucune donnée n'est perdue et que tout le parcours reste traçable. Puis traitées (nettoyage et filtrage des anomalies) avant d'être chargées dans le Data Warehouse

```text
┌──────────────┐         HTTP GET         ┌────────────────────────────────┐
│   WAQI API   │ ───────────────────────> │  GitHub Actions (Orchestrator) │
└──────────────┘                          └────────────────────────────────┘
                                                           │
                                                           ▼
                                         ┌──────────────────────────────────┐
                                         │  Staging Area / Raw Layer        │
                                         │  (Table: raw_air_quality)        │
                                         └──────────────────────────────────┘
                                                           │
                                                           ▼
                                         ┌──────────────────────────────────┐
                                         │  Transformation Layer            │
                                         │  (Script: transform.py)          │
                                         └──────────────────────────────────┘
                                                           │
                                                           ▼
                                         ┌──────────────────────────────────┐
                                         │  Analytics Layer (Data Warehouse)│
                                         │  Supabase (PostgreSQL)           │
                                         │  • dim_city     • dim_parameter  │
                                         │  • dim_date     • fact_air_quality│
                                         └──────────────────────────────────┘
```

## 2. Stack Technique & Décisions d'Ingénierie

### 2.1. Orchestration — GitHub Actions
Choisi pour automatiser l'exécution horaire du pipeline ETL (`.github/workflows/pipeline.yml`) de manière 100% et  sans gestion d'infrastructure lourde, tout en bénéficiant de logs d'exécution et d'alertes intégrés en cas d'échec.

### 2.2. Source de Données — WAQI API
Sélectionnée car elle fournit des mesures d'indices (AQI) et de polluants atmosphériques (`pm25`, `pm10`, `no2`, `so2`, `co`, `o3`) fiables et standardisées pour les 5 métropoles ciblées.

### 2.3. Couche de Traitement — Python Core (`extract.py` & `transform.py`)
Utilise `requests` pour l'extraction API, `pandas` pour le nettoyage/pivotement, `sqlalchemy` pour la persistance SQL, et `python-dotenv` pour la sécurité des clés.

### 2.4. Zone Brute / Landing Zone — Table `raw_air_quality` (Supabase)
Retenue pour conserver l'historique complet et immuable des réponses API brutes au format long (`city`, `parameter`, `value`, `unit`, `timestamp`) afin de garantir la traçabilité.

### 2.5. Base de Données / Data Warehouse — Supabase (PostgreSQL)
Adopté suite aux problèmes de timeout rencontrés sur Neon, offrant une instance PostgreSQL cloud stable et directement accessible.

## 3. Data Quality & Idempotence

### 3.1. Garantie d'Idempotence (UPSERT)
Une contrainte d'unicité SQL est appliquée sur le triplet `(city, parameter, timestamp)`. Toute ré-exécution du pipeline met à jour la ligne existante sans générer de doublons.

### 3.2. Détection d'Anomalies (`detect_outliers`)
Filtrage qualité au niveau de `transform.py`. Toute valeur située en dehors de la plage validée [0, 500] sur l'échelle AQI est automatiquement écartée avant le chargement.

## 4. Modélisation Dimensionnelle — Schéma en Étoile (Star Schema)

### 4.1. Table de Faits — `fact_air_quality`
Stocke les mesures quantitatives de pollution (valeurs AQI) associées aux clés étrangères des dimensions.

### 4.2. Tables de Dimensions — `dim_city`, `dim_parameter`, `dim_date`
Mis en place pour séparer les métriques des contextes descriptifs (géographie, typologie des polluants, grain temporel UTC), ce qui optimise les requêtes analytiques et la préparation des données pour l'IA.


======> jerena av eo oe aiza ho aiza daoy le zvtr tanisaina reo so hantanina am présentation
atao ze ville madio au lieu de ville maloto le izy fa azo lazaina ho mitovy ihany
bien le bonjour