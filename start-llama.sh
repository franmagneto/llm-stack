#!/bin/bash
# Wrapper para llama-server com auto-load opcional de modelo ao iniciar.
#
# Uso: start-llama.sh [args...]
#
# Variáveis de ambiente:
#   LLAMA_AUTO_LOAD_MODEL   true/false (default: true)
#   LLAMA_MODEL             nome do modelo para carregar (default: unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M)
#   LLAMA_SERVER_URL        URL do servidor (default: http://localhost:8080)
#   LLAMA_LOAD_RETRY      nº de tentativas antes de desistir (default: 10)
#   LLAMA_LOAD_INTERVAL_s intervalo entre tentativas em segundos (default: 1)

set -eu

DEFAULT_MODEL="unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M"

AUTO_LOAD="${LLAMA_AUTO_LOAD_MODEL:-true}"
MODEL="${LLAMA_MODEL:-$DEFAULT_MODEL}"
SERVER_URL="${LLAMA_SERVER_URL:-http://localhost:8080}"
RETRY="${LLAMA_LOAD_RETRY:-10}"
INTERVAL="${LLAMA_LOAD_INTERVAL_s:-1}"

# Iniciar llama-server em background
/app/llama-server "$@" &
SERVER_PID=$!

# Aguardar o servidor responder em /health
for ((i=0; i<60; i++)); do
    if curl -sf "$SERVER_URL/health" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Auto-load se habilitado
if [ "$AUTO_LOAD" = "true" ]; then
    echo "Loading model: $MODEL"
    for ((i=0; i<RETRY; i++)); do
        if RESPONSE=$(curl -sf -X POST "$SERVER_URL/models/load" \
            -H 'Content-Type: application/json' \
            -d "{\"model\":\"$MODEL\"}" 2>&1); then
            echo "Model loaded successfully: $MODEL"
            echo "$RESPONSE"
            break
        fi
        echo "Try $((i+1))/$RETRY failed, retrying in ${INTERVAL}s..."
        sleep "$INTERVAL"
    done
fi

# Esperar o server (recebe SIGHUP/SIGTERM corretamente)
wait $SERVER_PID
