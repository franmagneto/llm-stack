#!/usr/bin/env bash
set -euo pipefail

IMG="llama-metrics-tui:latest"
BUILD_CMD="podman"

# Detect docker se podman não existir
[ ! -x "$(command -v podman 2>/dev/null)" ] && BUILD_CMD="docker"

echo "Building container image..."
$BUILD_CMD build -t "$IMG" -f llama_metrics/Containerfile .

echo "Running TUI (container destroyed on exit)..."
$BUILD_CMD run --rm -it \
  --network host \
  -e TERM="${TERM:-xterm-256color}" \
  -e LLAMA_SERVER_URL="${LLAMA_SERVER_URL:-http://localhost:8080}" \
  -e LLAMA_MODEL="${LLAMA_MODEL:-unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M}" \
  "$IMG"
