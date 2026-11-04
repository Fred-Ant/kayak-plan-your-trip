# Plan your trip with Kayak

Projet du **bloc 1 – Construction et alimentation d'une infrastructure de gestion de données**
de la certification RNCP35288 *Concepteur développeur en science des données* (formation Jedha Fullstack Data Science).

## Contexte

L'équipe marketing de Kayak souhaite une application qui recommande les meilleures destinations
et les meilleurs hôtels en France, à partir de données réelles de **météo** et d'**hôtels**.
Le périmètre porte sur 35 villes françaises.

## Livrables

- Un fichier `.csv` enrichi (météo + hôtels) stocké dans un **Data Lake AWS S3**
- Une **base SQL AWS RDS (PostgreSQL)** contenant les mêmes données nettoyées
- Deux cartes : **Top-5 destinations** et **Top-20 hôtels**

## Architecture

*(schéma à compléter – étape 7)*

```
Nominatim (GPS) ─┐
OpenWeatherMap ──┼─> data/raw ──> S3 (raw/ , processed/) ──ETL──> RDS PostgreSQL ──> Cartes Plotly
Booking (Scrapy) ┘
```

## Arborescence

```
kayak-plan-your-trip/
├── notebooks/        # Étapes du projet, numérotées dans l'ordre d'exécution
├── scraping/         # Spider Scrapy pour Booking.com
├── sql/              # Schéma de la base de données
├── data/             # Fichiers locaux de travail (exclus de Git)
├── outputs/maps/     # Cartes produites
├── docs/             # Schémas, captures d'écran
├── .env.example      # Modèle de configuration (sans secret)
└── requirements.txt  # Dépendances Python
```

## Installation

```powershell
conda create -n kayak python=3.11 -y
conda activate kayak
pip install -r requirements.txt
copy .env.example .env    # puis renseigner les valeurs dans .env
```

## Sécurité

Aucune clé ni aucun identifiant n'est présent dans le code : ils sont lus depuis un fichier `.env`
local, exclu du dépôt par `.gitignore` (ou depuis les secrets Colab).

## Sources de données

- [Nominatim](https://nominatim.org/) – coordonnées GPS (OpenStreetMap)
- [OpenWeatherMap One Call API 3.0](https://openweathermap.org/api/one-call-3) – prévisions météo à 7 jours
- [Booking.com](https://www.booking.com/) – informations hôtels (scraping à visée pédagogique)
