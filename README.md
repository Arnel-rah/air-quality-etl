# Pipeline Qualité de l'Air – README du stockage

## 1. Objectif

Ce projet consiste à déployer un pipeline automatisé qui collecte en continu (24h/24) les données de qualité de l'air (AQI) pour 5 villes françaises.  

Les données sont stockées de manière structurée (zone brute + zone nettoyée) puis chargées dans un **data warehouse dimensionnel** hébergé sur Supabase (schéma en étoile), afin d’être consommées par le cours IA1.

Le pipeline est entièrement automatisé via **GitHub Actions** et continue de tourner après le rendu.


## 2. Villes couvertes

| Ville | Latitude | Longitude | Pays |
|---|---|---|---|
| Paris | 48.8566 | 2.3522 | France |
| Marseille | 43.2965 | 5.3698 | France |
| Lyon | 45.7640 | 4.8357 | France |
| Toulouse | 43.6047 | 1.4442 | France |
| Nice | 43.7102 | 7.2620 | France |

Ces cinq villes couvrent des profils géographiques et de pollution variés....

## 3. Architecture du pipeline
 
Voir **[ARCHITECTURE.md](ARCHITECTURE.md)** pour le détail complet de la stack et les justifications techniques.
 
```
API WAQI (World Air Quality Index)
        │  collecte horaire par ville
        ▼
GitHub Actions (orchestrateur, cron horaire)
        │
        ▼
Supabase — table raw_air_quality
   (1 ligne = 1 ville + 1 polluant + 1 timestamp)
        │
        ▼
transform.py (script de transformation, idempotent)
        │
        ▼
Supabase — Data Warehouse (schéma en étoile)
   dim_city · dim_parameter · dim_date · fact_air_quality
```
| Composant       | Choix                  | Justification                                                     |
|-----------------|------------------------|--------------------------------------------------------------------|
| Source de données | API WAQI              | Mesures d'indices et de polluants atmosphériques fiables et standardisées pour les 5 métropoles ciblées |
| Orchestrateur   | GitHub Actions (`.github/workflows/pipeline.yml`) | Automatise l'exécution du pipeline ETL de façon 100 % autonome, sans surcoût ni gestion d'infrastructure |
| Stockage brut   | Table `raw_air_quality` (Supabase) | Conserve l'historique complet et immuable des réponses API brutes, garantit la traçabilité des données |
| Data Warehouse  | Supabase (PostgreSQL)  | Retenu après des problèmes de timeout rencontrés sur une première instance Neon ; offre une base PostgreSQL cloud stable et directement accessible |
| Modélisation    | Schéma en étoile       | Sépare les données quantitatives (faits) des contextes descriptifs (`dim_city`, `dim_parameter`, `dim_date`), ce qui optimise les requêtes analytiques et la préparation des données pour IA1 |
 
> Historique d'exécution : le workflow `.github/workflows/pipeline.yml` s'exécute automatiquement selon une planification cron (déclenchement `Scheduled`), sans intervention manuelle. Au [date de vérification], l'historique GitHub Actions du dépôt comptait déjà plusieurs dizaines d'exécutions réussies. [Équipe : compléter avec le nombre exact de runs et confirmer qu'ils s'étalent sur au moins 5 jours différents, via l'onglet **Actions** du dépôt.]

## 4. Contrat de données – table `raw_air_quality`
 
Le projet n'utilise pas de fichiers plats `raw/`/`clean/` : la zone brute/propre est la table Supabase `raw_air_quality`, qui joue ce rôle et sert de source unique pour reconstruire le warehouse à chaque exécution de `transform.py`.
 
| Colonne     | Type     | Description / Unité                                                        | Exemple                  |
|-------------|----------|------------------------------------------------------------------------------|---------------------------|
| `id`        | bigint   | Identifiant technique auto-incrémenté                                       | 1                         |
| `timestamp` | datetime | Horodatage de la mesure, fuseau UTC (ISO 8601)                               | 2026-07-23T05:00:00+00:00 |
| `city`      | text     | Nom de la ville                                                               | Paris                     |
| `parameter` | text     | Polluant ou indice mesuré : `aqi_global`, `pm25`, `pm10`, `no2`, `so2`, `co`, `o3` | pm25                  |
| `value`     | numeric  | Valeur mesurée, sur l'échelle AQI fournie par WAQI                            | 13.0                      |
| `unit`      | text     | Unité déclarée par la source                                                  | AQI                       |
| `inserted_at` | timestamptz | Horodatage technique d'insertion en base                                | 2026-07-23T07:54:20+00:00 |
 
**Granularité** : une ligne par ville + heure + polluant (format long). Pour obtenir une vue "une ligne par ville-heure avec un polluant par colonne", il suffit de pivoter cette table sur `parameter`.
 
**Déduplication** : contrainte d'unicité Supabase sur `(city, parameter, timestamp)` — un upsert réinsère la même mesure sans jamais créer de doublon, même en cas de relance du script.
 
**Qualité des données** : toute valeur en dehors de la plage `[0, 500]` (bornes de l'échelle AQI) est automatiquement écartée par la fonction `detect_outliers` avant chargement dans le warehouse.


## 5. Connexion a la base 

## Type de base : PostgreSQL managé (Supabase)
## Projet Supabase : air-quality-etl


Les identifiants de connexion (SUPABASE_URL, SUPABASE_KEY, WAQI_API_TOKEN) sont exclusivement stockés dans les GitHub Secrets et dans un fichier .env local non versionné. Aucune clé n'apparaît dans le code ni dans l'historique Git.
## 6. Période couverte

- **Début** : 23 juillet 2026 à 04h43 (UTC)
- **Fin** : en cours (collecte active)
- **Fréquence** : toutes les heures

## Schéma du Data Warehouse

Modélisation en **schéma étoile**.

### Table de faits — `fact_air_quality`

| Colonne | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Identifiant unique |
| `city_id` | INTEGER (FK) | Référence vers `dim_city` |
| `parameter_id` | INTEGER (FK) | Référence vers `dim_parameter` |
| `date_id` | INTEGER (FK) | Référence vers `dim_date` |
| `value` | FLOAT | Valeur mesurée (AQI ou polluant) |
| `inserted_at` | TIMESTAMP | Date d'insertion en base |

### Dimension ville — `dim_city`

| Colonne | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Identifiant unique |
| `name` | VARCHAR | Nom de la ville |
| `country` | VARCHAR | Pays (France) |
| `latitude` | FLOAT | Latitude géographique |
| `longitude` | FLOAT | Longitude géographique |

### Dimension temps — `dim_date`

| Colonne | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Identifiant unique |
| `date` | DATE | Date complète |
| `hour` | INTEGER | Heure (0–23) |
| `day_of_week` | VARCHAR | Jour de la semaine |
| `is_weekend` | BOOLEAN | Vrai si samedi ou dimanche |
| `month` | INTEGER | Mois (1–12) |
| `year` | INTEGER | Année |

### Dimension paramètre — `dim_parameter`

| Colonne | Type | Description |
|---|---|---|
| `id` | INTEGER (PK) | Identifiant unique |
| `name` | VARCHAR | Nom du polluant (aqi_global, pm25, pm10, no2, so2, co, o3) |
| `unit` | VARCHAR | Unité de mesure (AQI) |
| `description` | VARCHAR | Description du paramètre |

---

## Trous connus

Aucun trou identifié à ce jour. Les écarts éventuels peuvent être dus à :

| Cause | Impact |
|---|---|
| Indisponibilité de l'API WAQI | Données manquantes pour certaines heures |
| Polluant non disponible pour une ville | Valeur absente pour ce paramètre |

---