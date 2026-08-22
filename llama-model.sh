#!/bin/sh
set -eu

SERVER="${LLAMA_SERVER_URL:-http://localhost:8080}"
DEFAULT_MODEL="${LLAMA_MODEL:-unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M}"

COMMAND=""
ARG_MODEL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --server)
            SERVER="$2"; shift 2 || { echo "Usage: llama-model {list|load|unload} [model]" >&2; exit 1; }
            ;;
        list|load|unload)
            COMMAND="$1"; shift ;;
        *)
            ARG_MODEL="$1"; shift ;;
    esac
done

[ -n "$COMMAND" ] || { echo "Usage: llama-model {list|load|unload} [model]" >&2; exit 1; }

case "$COMMAND" in
    list)
        curl -sf "$SERVER/models" | \
        jq -r '.data[] | "\(.status.value) \(.id)"'
        ;;
    load)
        curl -sf -X POST "$SERVER/models/load" \
            -H 'Content-Type: application/json' \
            -d "{\"model\":\"${ARG_MODEL:-$DEFAULT_MODEL}\"}" | jq .
        ;;
    unload)
        if [ -n "$ARG_MODEL" ]; then
            curl -sf -X POST "$SERVER/models/unload" \
                -H 'Content-Type: application/json' \
                -d "{\"model\":\"$ARG_MODEL\"}" | jq .
        else
            curl -sf "$SERVER/models" | jq -r '.data[] | select(.status.value == "loaded") | .id' | while read -r model; do
                curl -sf -X POST "$SERVER/models/unload" \
                    -H 'Content-Type: application/json' \
                    -d "{\"model\":\"$model\"}" | jq .
            done
        fi
        ;;
esac
