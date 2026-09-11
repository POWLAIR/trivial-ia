"""Configuration centrale du projet.

Tous les chemins, URL et paramètres d'exécution vivent ici : aucun autre module
ne contient de chemin ni d'URL en dur. Conséquence pratique, changer de runtime
LLM (LM Studio vers Ollama, par exemple) ne coûte qu'une variable d'environnement
et ne touche pas au code du runner.
"""

from __future__ import annotations

import json
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
# Compte global en un seul appel : donne le nombre de questions *vérifiées*
# par catégorie, seules réellement servies par l'API.
OPENTDB_COUNT_GLOBAL_URL = "https://opentdb.com/api_count_global.php"
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
# Modèles retenus : deux tailles de la famille gemma-3. Les alternatives du
# catalogue LM Studio (qwen3, phi-4-mini-reasoning) sont des modèles à
# raisonnement, dont le `content` reste vide sous un budget de 32 tokens.
# La valeur est le motif de nom du fichier GGUF, tel que téléchargé par `lms get`.
MODELS = {
    "gemma-3-1b": "gemma-3-1B-it-QAT-Q4_0.gguf",
    "gemma-3-4b": "gemma-3-4b-it-Q4_K_M.gguf",
}

# --- Moteur d'inférence ---------------------------------------------------

# LM Studio sert à télécharger et gérer les modèles, mais son serveur impose
# `--threads 1` sur cette machine — ni la CLI ni son SDK n'exposent le réglage.
# On lance donc directement le llama.cpp qu'il embarque. Mesuré : 3x de débit
# (gemma-3-1b de 3,4 s à 1,13 s par question), à moteur et modèles identiques.
LMSTUDIO_HOME = Path.home() / ".lmstudio"
MODELS_DIR = LMSTUDIO_HOME / "models"
BACKENDS_DIR = LMSTUDIO_HOME / "extensions" / "backends"

LLAMA_THREADS = 4
LLAMA_CTX_SIZE = 2048  # 8192 par défaut coûte cher en évaluation de prompt
LLAMA_PORT = 1235


BACKEND_PREFERENCE_FILE = LMSTUDIO_HOME / ".internal" / "backend-preferences-v1.json"


def llama_server_bin() -> Path:
    """Localise le binaire llama-server fourni par LM Studio.

    On suit le backend que LM Studio a lui-même retenu, lu dans ses préférences.
    Prendre le premier venu choisirait le backend Vulkan, alors que cette machine
    n'a pas de GPU exploitable : c'est la variante `avx2` qui convient.
    """
    preferred = None
    if BACKEND_PREFERENCE_FILE.exists():
        entries = json.loads(BACKEND_PREFERENCE_FILE.read_text())
        for entry in entries:
            if entry.get("model_format") == "gguf":
                preferred = f"{entry['name']}-{entry['version']}"
                break

    if preferred:
        candidate = BACKENDS_DIR / preferred / "llama-server"
        if candidate.exists():
            return candidate

    candidates = sorted(BACKENDS_DIR.glob("llama.cpp-*/llama-server"))
    if not candidates:
        raise FileNotFoundError(f"aucun llama-server sous {BACKENDS_DIR}")
    return candidates[0]


def model_path(key: str) -> Path:
    """Chemin du fichier GGUF d'un modèle du benchmark."""
    try:
        pattern = MODELS[key]
    except KeyError:
        raise ValueError(f"modèle inconnu : {key} (connus : {sorted(MODELS)})") from None
    matches = [p for p in MODELS_DIR.rglob(pattern) if "mmproj" not in p.name]
    if not matches:
        raise FileNotFoundError(f"{pattern} introuvable — lancez `lms get -y --gguf google/{key}`")
    return matches[0]
