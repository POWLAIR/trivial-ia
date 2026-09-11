#!/usr/bin/env bash
# Lance le benchmark sur tous les modèles, un à la fois.
#
# LM Studio sert à gérer les modèles (`lms get`, `lms ls`), mais son serveur
# impose --threads 1 sur cette machine, sans réglage possible. On lance donc
# directement le llama.cpp qu'il embarque, avec tous les cœurs : même moteur,
# mêmes modèles, 3x de débit.
#
# Usage : scripts/run_benchmark.sh [N_QUESTIONS] [PROMPT_VERSION]

set -euo pipefail
cd "$(dirname "$0")/.."

LIMIT="${1:-550}"
PROMPT="${2:-v3}"
PYTHON="${PYTHON:-.venv/bin/python}"

PORT=$($PYTHON -c 'from trivia_bench import config; print(config.LLAMA_PORT)')
BIN=$($PYTHON -c 'from trivia_bench import config; print(config.llama_server_bin())')
THREADS=$($PYTHON -c 'from trivia_bench import config; print(config.LLAMA_THREADS)')
CTX=$($PYTHON -c 'from trivia_bench import config; print(config.LLAMA_CTX_SIZE)')
MODELS=$($PYTHON -c 'from trivia_bench import config; print(" ".join(config.MODELS))')

server_pid=""
cleanup() { [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true; }
trap cleanup EXIT

for key in $MODELS; do
  echo "===== $key"
  gguf=$($PYTHON -c "from trivia_bench import config; print(config.model_path('$key'))")

  # Un seul modèle résident à la fois : deux modèles chargés saturent la RAM et
  # response_time mesurerait alors la contention, pas le modèle.
  cleanup; server_pid=""
  setsid "$BIN" --model "$gguf" --threads "$THREADS" --ctx-size "$CTX" \
        --port "$PORT" --host 127.0.0.1 >"/tmp/llama-$key.log" 2>&1 &
  server_pid=$!

  printf "  chargement"
  for _ in $(seq 1 90); do
    if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"'; then
      echo " ok"; break
    fi
    printf "."; sleep 2
  done

  $PYTHON -m trivia_bench.enrich.runner --model "$key" --prompt-version "$PROMPT" --limit "$LIMIT"
done

echo "Terminé."
