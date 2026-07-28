# Pipeline Qualité de l'Air – README du stockage

## 1. Objectif

Ce projet déploie un pipeline automatisé qui collecte, 24h/24, des données de qualité de l'air (AQI) pour **5 villes françaises**, les stocke dans une base **Supabase (PostgreSQL)**, puis les restructure selon une **modélisation dimensionnelle en étoile**. Le pipeline est orchestré par **GitHub Actions** et conçu pour continuer à tourner après le rendu, afin d'alimenter le cours IA1 au fil de l'eau.

Ce document décrit précisément le contenu du stockage : villes couvertes, structure des données, schéma du warehouse, période couverte et modalités de connexion — de façon à ce que toute personne extérieure au groupe puisse exploiter les données sans ambiguïté.

## 2. Villes choisies

| Ville     | Pays   | Latitude | Longitude |
|-----------|--------|----------|-----------|
| Paris     | France | 48.8566  | 2.3522    |
| Marseille | France | 43.2965  | 5.3698    |
| Lyon      | France | 45.7640  | 4.8357    |
| Toulouse  | France | 43.6047  | 1.4442    |
| Nice      | France | 43.7102  | 7.2620    |

Ces cinq villes couvrent des profils géographiques et de pollution variés (grande métropole intérieure, villes portuaires méditerranéennes, agglomération du sud-ouest), ce qui permet des comparaisons pertinentes pour les analyses en aval.

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

## 5. Data Warehouse – Modélisation dimensionnelle

### Modèle choisi : schéma en étoile

Le schéma retenu place `fact_air_quality` au centre, reliée à trois dimensions : `dim_city`, `dim_parameter` et `dim_date`. Choisir un polluant par ligne (plutôt qu'une colonne par polluant) rend le modèle extensible : si l'API WAQI ajoute un nouveau polluant demain, il suffit d'une nouvelle ligne dans `dim_parameter`, sans modifier le schéma de la table de faits. Ce choix respecte strictement les règles vues en cours : aucune mesure dans les dimensions, aucune colonne descriptive dans la table de faits.

### Table de faits : `fact_air_quality`

| Colonne        | Type      | Rôle                                            |
|----------------|-----------|--------------------------------------------------|
| `id`           | bigserial | Clé primaire technique                            |
| `city_id`      | integer   | Clé étrangère → `dim_city`                       |
| `parameter_id` | integer   | Clé étrangère → `dim_parameter`                  |
| `date_id`      | integer   | Clé étrangère → `dim_date`                       |
| `value`        | numeric   | Mesure (indice AQI ou concentration du polluant) |
| `inserted_at`  | timestamptz | Horodatage technique d'insertion                |

Contrainte d'unicité : `(city_id, parameter_id, date_id)`.

### Dimension ville : `dim_city`

| Colonne     | Type   | Description             |
|-------------|--------|---------------------------|
| `city_id`   | serial | Clé primaire               |
| `city_name` | text   | Nom de la ville (unique)   |
| `country`   | text   | Pays (`FR` par défaut)     |

> **Limite connue et assumée** : les coordonnées latitude/longitude ne sont pour l'instant pas stockées dans cette table, mais uniquement documentées en section 2 de ce README. [Équipe : à corriger avant le rendu — ajout de deux colonnes `latitude` et `longitude` à `dim_city`, remplies avec les valeurs de la section 2.]

### Dimension polluant : `dim_parameter`

| Colonne          | Type   | Description                                       |
|------------------|--------|------------------------------------------------------|
| `parameter_id`   | serial | Clé primaire                                          |
| `parameter_name` | text   | Nom du polluant (`aqi_global`, `pm25`, `pm10`, `no2`, `so2`, `co`, `o3`) |
| `unit`           | text   | Unité déclarée par la source                          |

### Dimension temps : `dim_date`

| Colonne          | Type        | Description                                     |
|------------------|-------------|----------------------------------------------------|
| `date_id`        | serial      | Clé primaire                                        |
| `full_timestamp` | timestamptz | Horodatage complet (unique)                         |
| `date`           | date        | Date                                                |
| `year`           | integer     | Année                                               |
| `month`          | integer     | Mois (1–12)                                         |
| `day`            | integer     | Jour du mois                                        |
| `hour`           | integer     | Heure (0–23)                                        |
| `day_of_week`    | integer     | Jour de la semaine (0 = lundi … 6 = dimanche)        |

> **Limite connue et assumée** : la colonne `is_weekend` n'est pas matérialisée. Elle se déduit directement en SQL via `day_of_week IN (5, 6)`. [Équipe : à corriger avant le rendu si le temps le permet — ajout d'une colonne `is_weekend boolean`.]

### Cohérence des volumes

Le modèle étant en format long (un polluant par ligne), le nombre de lignes attendu dans la table de faits suit la formule :

> **nombre de villes × nombre d'heures couvertes × nombre de polluants mesurés (7)**

et non `villes × heures` seul, comme dans un modèle large classique. Cette particularité est documentée ici pour éviter toute ambiguïté lors de la lecture par IA1.

## 6. Période couverte

- **Backfill** : [Équipe : indiquer ici la période réelle couverte par le script de backfill — du `YYYY-MM-DD` au `YYYY-MM-DD` — après vérification dans `dim_date`]
- **Collecte en continu** : depuis le [Équipe : date de mise en route effective du workflow GitHub Actions en cron horaire]

## 7. Trous connus

| Période / Heure | Ville(s) concernée(s) | Cause |
|-------------------|-------------------------|--------|
| [Équipe : à documenter après vérification des logs GitHub Actions] | | |

> Aucune donnée manquante n'a été reconstituée artificiellement : les trous reflètent fidèlement les échecs de collecte réels (quota API, erreurs réseau, etc.).

## 8. Connexion à la base de données

- **Type de base** : PostgreSQL managé (Supabase)
- **Projet Supabase** : `air-quality-etl`
- **Tables** :
  - `raw_air_quality` — zone brute/propre, une ligne par ville + heure + polluant
  - `dim_city`, `dim_parameter`, `dim_date`, `fact_air_quality` — Data Warehouse
- **Script de collecte** : `extract.py`, déclenché automatiquement par GitHub Actions
- **Script de transformation et chargement** : `transform.py`, rejouable et idempotent (upserts sur clés naturelles)

Les identifiants de connexion (`SUPABASE_URL`, `SUPABASE_KEY`, `WAQI_API_TOKEN`) sont exclusivement stockés dans les **GitHub Secrets** et dans un fichier `.env` local non versionné. Aucune clé n'apparaît dans le code ni dans l'historique Git.

## 9. Relancer le pipeline

```bash
python extract.py       # collecte les mesures horaires depuis WAQI
python transform.py     # reconstruit le warehouse depuis raw_air_quality
```

Ces deux étapes sont également exécutées automatiquement par le workflow GitHub Actions défini dans `.github/workflows/`.

## 10. Structure du dépôt

```
.
├── .github/
│   └── workflows/          # Orchestration GitHub Actions (cron horaire)
├── ARCHITECTURE.md
├── README.md
├── sql/
│   └── schema.sql          # Définition des tables du warehouse
├── scripts/
│   ├── extract.py          # Collecte des données via l'API WAQI
│   └── transform.py        # Transformation et chargement du warehouse
├── .env.example
└── docs/                   # Captures d'écran, preuves d'exécution
```