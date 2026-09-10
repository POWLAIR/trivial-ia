"""Configuration centrale du projet.

Tous les chemins, URL et paramètres d'exécution vivent ici : aucun autre module
ne contient de chemin ni d'URL en dur. Conséquence pratique, changer de runtime
LLM (LM Studio vers Ollama, par exemple) ne coûte qu'une variable d'environnement
et ne touche pas au code du runner.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Arborescence ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

QUESTIONS_RAW_CSV = BRONZE_DIR / "questions_raw.csv"
BRONZE_ARCHIVE_DIR = BRONZE_DIR / "archive"
INGESTION_REPORT_JSON = BRONZE_DIR / "_ingestion_report.json"

QUESTIONS_PARQUET = SILVER_DIR / "questions.parquet"
AI_ANSWERS_PARQUET = SILVER_DIR / "ai_answers.parquet"
AI_ANSWERS_PARTS_DIR = SILVER_DIR / "_ai_answers_parts"

BENCHMARK_DUCKDB = GOLD_DIR / "benchmark.duckdb"

# --- API Open Trivia Database ---------------------------------------------

OPENTDB_API_URL = "https://opentdb.com/api.php"
OPENTDB_CATEGORY_URL = "https://opentdb.com/api_category.php"
OPENTDB_COUNT_URL = "https://opentdb.com/api_count.php"
OPENTDB_TOKEN_URL = "https://opentdb.com/api_token.php"

# L'API plafonne à 50 questions par appel et n'expose aucun offset : le balayage
# exhaustif passe obligatoirement par un jeton de session.
OPENTDB_BATCH_SIZE = 50

# Limite de débit annoncée : 1 requête toutes les 5 s par IP. La marge évite de
# déclencher un response_code 5 sur une horloge légèrement décalée.
OPENTDB_MIN_INTERVAL = 5.2
OPENTDB_MAX_RETRIES = 5
OPENTDB_BACKOFF_BASE = 5.0

# url3986 se décode de façon déterministe, contrairement à l'encodage HTML par
# défaut. Le décodage lui-même appartient à la couche silver, pas à l'ingestion.
OPENTDB_ENCODING = "url3986"

HTTP_TIMEOUT = 30

# --- Runtime LLM ----------------------------------------------------------

# Endpoint compatible OpenAI. LM Studio écoute sur 1234, Ollama sur 11434 :
# la même valeur pilote les deux.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
LLM_TIMEOUT = 120

# Paramètres figés du benchmark. Les modifier invalide toute comparaison avec
# les exécutions précédentes : dans ce cas, tout relancer.
TEMPERATURE = 0
SEED = 42
MAX_TOKENS = 32

# --- Enrichissement -------------------------------------------------------

# Les résultats sont écrits par fragments de cette taille : une interruption ne
# fait perdre au plus qu'un fragment.
BATCH_SIZE = 100

# Au-delà d'un worker, plusieurs requêtes se disputent le CPU et response_time
# mesure la contention plutôt que la performance du modèle.
DEFAULT_WORKERS = 1

# Seuil de la règle « fuzzy » de la cascade de matching.
FUZZY_THRESHOLD = 0.90

# En deçà de cet effectif, l'intervalle de confiance est trop large pour publier
# un taux.
MIN_SAMPLE_FOR_RATE = 30

# Taille de l'échantillon stratifié utilisé pour comparer les prompts.
PROMPT_SAMPLE_SIZE = 300

# --- Modèles --------------------------------------------------------------

# Clés indicatives. La clé qui fait foi est celle listée par `lms ls` : elle
# dépend de la quantification réellement téléchargée.
#
# Trio calibré pour la machine du projet (i7-8550U, 4 cœurs, pas de GPU) :
# trois tailles nettement séparées pour que l'axe « effet de la taille » reste
# analysable, tout en restant exécutables sur ce CPU.
DEFAULT_MODELS = (
    "llama-3.2-1b-instruct",
    "qwen2.5-1.5b-instruct",
    "llama-3.2-3b-instruct",
)
