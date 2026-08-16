#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

case "${1:-help}" in
    build|rebuild)
        echo "Building TUI container image..."
        podman compose --profile metrics build
        ;;
    run)
        echo "Starting TUI dashboard (Ctrl+C to exit)..."
        podman compose --profile metrics run --rm llama-metrics
        ;;
    logs)
        shift
        podman compose --profile metrics logs --tail=100 "$@"
        ;;
    help|*)
        cat <<EOF
Usage: $0 {build|run|logs}

TUI metrics dashboard for llama-server (log-based polling).

Commands:
  build  Build TUI container image
  run    Start TUI dashboard (foreground, Ctrl+C to exit)
  logs   Show recent TUI container logs

Examples:
  $0 run          # open TUI dashboard
  $0 logs -f      # follow TUI logs

Note: llama-server + Open WebUI must be running separately:
  podman compose up -d
EOF
        ;;
esac
