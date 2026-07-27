#Architecture Technique — Pipeline ETL Qualité de l'Air

## Stack Choisie & Justifications

### 1. Orchestrateur — GitHub Actions
Choisi pour automatiser l'exécution quotidienne du pipeline ETL (`.github/workflows/pipeline.yml`) de manière 100% autonome, sans surcoût ni gestion d'infrastructure lourde.

### 2. Source de Données — WAQI API
Sélectionnée car elle fournit des mesures d'indices et de polluants atmosphériques fiables et standardisées pour les 5 métropoles ciblées.

### 3. Stockage Brut — Table `raw_air_quality` (Supabase)
Retenu pour conserver l'historique complet et immuable des réponses API brutes afin de garantir la traçabilité des données.

### 4. Base de Données / Data Warehouse — Supabase (PostgreSQL)
Adopté suite aux problèmes de timeout rencontrés sur Neon , offrant une instance PostgreSQL cloud stable et directement accessible.

### 5. Modélisation — Schéma en Étoile (Star Schema)
Mis en place pour séparer les données quantitatives des contextes descriptifs (`dim_city`, `dim_parameter`, `dim_date`, `fact_air_quality`), ce qui optimise les requêtes analytiques et la préparation des données pour l'IA.
