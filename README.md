# Pipeline Qualité de l'Air — Documentation du stockage

## 1. Objectif

Ce projet déploie un pipeline automatisé qui collecte, 24h/24, des données de qualité de l'air (AQI) pour cinq villes françaises, les stocke dans une base Supabase (PostgreSQL), puis les restructure selon une modélisation dimensionnelle en étoile. Le pipeline est orchestré par GitHub Actions et conçu pour continuer à tourner après le rendu, afin d'alimenter le cours IA1 au fil de l'eau.

Ce document décrit le contenu exact du stockage — villes couvertes, structure des données, schéma du warehouse, période couverte, limites connues et modalités de connexion — de façon à ce que toute personne extérieure au groupe puisse exploiter les données sans ambiguïté.

## 2. Villes couvertes

| Ville | Pays | Latitude | Longitude |
|---|---|---|---|
| Paris | France | 48.8566 | 2.3522 |
| Marseille | France | 43.2965 | 5.3698 |
| Lyon | France | 45.7640 | 4.8357 |
| Toulouse | France | 43.6047 | 1.4442 |
| Nice | France | 43.7102 | 7.2620 |

Ces cinq villes couvrent des profils géographiques et de pollution variés — une grande métropole intérieure, deux villes portuaires méditerranéennes et une agglomération du sud-ouest — ce qui permet des comparaisons pertinentes pour les analyses en aval.

## 3. Architecture du pipeline

La stack complète (orchestrateur, stockage, base de données) et la justification de chaque choix sont détaillées dans [`ARCHITECTURE.md`](./ARCHITECTURE.md). En résumé : API WAQI → GitHub Actions (cron horaire) → Supabase `raw_air_quality` → `transform.py` → Data Warehouse en étoile (`dim_city`, `dim_parameter`, `dim_date`, `fact_air_quality`).

**Point d'attention sur le raw/clean.** Le stockage brut est implémenté sous forme de table Supabase (`raw_air_quality`) plutôt que de dossiers `raw/`/`clean/` avec des fichiers physiques. Cette table n'est jamais modifiée et le Data Warehouse est intégralement reconstructible à partir d'elle.

**Historique d'exécution.** L'historique complet des exécutions du pipeline via GitHub Actions est disponible sous forme de capture dans le dossier `docs/`.

## 4. Contrat de données — table `raw_air_quality`

La zone brute est portée par la table Supabase `raw_air_quality`, qui joue le rôle de sauvegarde immuable et sert de source unique pour reconstruire le warehouse à chaque exécution de `transform.py`.

| Colonne | Type | Description / unité | Exemple |
|---|---|---|---|
| `id` | bigint | Identifiant technique auto-incrémenté | 1 |
| `timestamp` | timestamptz | Horodatage de la mesure, fuseau UTC (ISO 8601) | 2026-07-23T05:00:00+00:00 |
| `city` | text | Nom de la ville | Paris |
| `parameter` | text | Polluant ou indice mesuré : `aqi_global`, `pm25`, `pm10`, `no2`, `so2`, `co`, `o3` | pm25 |
| `value` | numeric | Valeur mesurée, sur l'échelle AQI fournie par WAQI | 13.0 |
| `unit` | text | Unité déclarée par la source | AQI |
| `inserted_at` | timestamptz | Horodatage technique d'insertion en base | 2026-07-23T07:54:20+00:00 |

**Granularité.** Une ligne par ville, heure et polluant (format long). Pour obtenir une vue « une ligne par ville-heure avec un polluant par colonne », il suffit de pivoter cette table sur `parameter`.

**Déduplication.** Contrainte d'unicité Supabase sur `(city, parameter, timestamp)` — un upsert réinsère la même mesure sans jamais créer de doublon, même en cas de relance du script d'extraction.

**Qualité des données.** Une fonction `detect_outliers` existe dans `transform.py` et filtre les valeurs hors de la plage `[0, 500]` (bornes de l'échelle AQI). *[Équipe : à confirmer — cette fonction n'est, en l'état du code, pas encore appelée dans le flux d'exécution principal ; vérifier son intégration avant d'affirmer que le filtrage est actif en production.]*

**Note sur les scripts d'extraction.** Le pipeline actif utilise `extract.py` (API WAQI), qui alimente directement `raw_air_quality`. Un second script, `extract_air_quality.py` (API OpenWeatherMap), écrit dans une table distincte (`air_quality_realtime`) non consommée par `transform.py`. *[Équipe : clarifier si ce second script est un reliquat à retirer du dépôt ou s'il a un usage prévu.]*

## 5. Data Warehouse — modélisation dimensionnelle

### Modèle retenu : schéma en étoile

`fact_air_quality` est reliée à trois dimensions : `dim_city`, `dim_parameter` et `dim_date`. Traiter chaque polluant comme une ligne (plutôt qu'une colonne par polluant) rend le modèle extensible : si l'API WAQI ajoute un nouveau polluant, une nouvelle ligne dans `dim_parameter` suffit, sans modifier le schéma de la table de faits. Ce choix respecte les règles vues en cours : aucune mesure dans les dimensions, aucune colonne descriptive dans la table de faits.

### Table de faits — `fact_air_quality`

| Colonne | Type | Rôle |
|---|---|---|
| `id` | bigserial | Clé primaire technique |
| `city_id` | integer | Clé étrangère → `dim_city` |
| `parameter_id` | integer | Clé étrangère → `dim_parameter` |
| `date_id` | integer | Clé étrangère → `dim_date` |
| `value` | numeric | Mesure (indice AQI ou concentration du polluant) |
| `inserted_at` | timestamptz | Horodatage technique d'insertion |

Contrainte d'unicité : `(city_id, parameter_id, date_id)`.

### Dimension ville — `dim_city`

| Colonne | Type | Description |
|---|---|---|
| `city_id` | serial | Clé primaire |
| `city_name` | text | Nom de la ville (unique) |
| `country` | text | Pays |
| `latitude` | numeric | Latitude géographique |
| `longitude` | numeric | Longitude géographique |

### Dimension polluant — `dim_parameter`

| Colonne | Type | Description |
|---|---|---|
| `parameter_id` | serial | Clé primaire |
| `parameter_name` | text | Nom du polluant (`aqi_global`, `pm25`, `pm10`, `no2`, `so2`, `co`, `o3`) |
| `unit` | text | Unité déclarée par la source |

### Dimension temps — `dim_date`

| Colonne | Type | Description |
|---|---|---|
| `date_id` | serial | Clé primaire |
| `full_timestamp` | timestamptz | Horodatage complet (unique) |
| `date` | date | Date |
| `year` | integer | Année |
| `month` | integer | Mois (1–12) |
| `day` | integer | Jour du mois |
| `hour` | integer | Heure (0–23) |
| `day_of_week` | integer | Jour de la semaine (0 = lundi … 6 = dimanche) |
| `is_weekend` | boolean | Vrai si le jour est un samedi ou dimanche |

### Cohérence des volumes

Le modèle étant en format long (un polluant par ligne), le nombre de lignes attendu dans la table de faits suit la formule :

```
nombre de villes × nombre d'heures couvertes × nombre de polluants mesurés (7)
```

et non villes × heures seul, comme dans un modèle large classique. Cette particularité est documentée ici pour éviter toute ambiguïté lors de la lecture par IA1.

## 6. Période couverte

## 6. Période couverte

- **Backfill / Historique** : Du 29 juillet 2025 au 30 juillet 2026(dernière mis à jour).
- **Collecte en continu** : Activée et exécutée en continu via un workflow GitHub Actions automatisé en cron horaire (toutes les heures).

## 7. Trous connus et données manquantes

Aucune donnée manquante n'a été reconstituée artificiellement : les trous listés ci-dessous reflètent fidèlement les interruptions réelles (indisponibilité de l'API, coupures réseau ou maintenance).

| Période / Heure de début | Fin de l'interruption | Durée | Cause |
|---|---|---|---|
| 2026-06-29 00:00 | 2026-07-23 04:00 | 24 jours | Interruption prolongée / arrêt du workflow |
| 2026-07-23 05:00 | 2026-07-23 07:00 | 2 heures | Micro-coupure technique |

## 8. Connexion à la base de données

- **Type de base** : PostgreSQL managé (Supabase)
- **Projet Supabase** : `air-quality-etl`
- **Tables** :
  - `raw_air_quality` — zone brute, une ligne par ville, heure et polluant
  - `dim_city`, `dim_parameter`, `dim_date`, `fact_air_quality` — Data Warehouse
- **Script de collecte** : `extract.py` (API WAQI), déclenché automatiquement par GitHub Actions
- **Script de transformation et chargement** : `transform.py`, rejouable et idempotent (upserts sur clés naturelles)

Les identifiants de connexion (`SUPABASE_URL`, `SUPABASE_KEY`, `WAQI_API_TOKEN`) sont exclusivement stockés dans les GitHub Secrets et dans un fichier `.env` local non versionné. Aucune clé n'apparaît dans le code ni dans l'historique Git.

## 9. Relancer le pipeline

```bash
python extract.py       # collecte les mesures horaires depuis WAQI
python transform.py     # reconstruit le warehouse depuis raw_air_quality
```

Ces deux étapes sont également exécutées automatiquement par le workflow GitHub Actions défini dans `.github/workflows/`.

---

