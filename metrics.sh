#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

case "${1:-help}" in
    build)
        echo "Building TUI container image..."
        podman compose --profile metrics build
        ;;
    up)
        echo "Starting llama-server + Open WebUI..."
        podman compose up -d
        ;;
    run)
        echo "Starting TUI (Ctrl+C to exit)..."
        podman compose --profile metrics run --rm llama-metrics
        ;;
    down)
        echo "Stopping llama-server + Open WebUI..."
        podman compose down
        ;;
    restart)
        podman compose down
        podman compose up -d
        ;;
    logs)
        shift
        podman compose --profile metrics logs --tail=100 "$@"
        ;;
    help|*)
        cat <<EOF
Usage: $0 {build|up|run|down|restart|logs}

Commands:
  build   Build TUI container image
  up      Start llama-server + Open WebUI in background
  run     Start TUI metrics dashboard (foreground, Ctrl+C to exit)
  down    Stop all containers
  restart Stop and restart all containers
  logs    Show recent TUI container logs (pass additional args)

Examples:
  $0 up           # start server + webui
  $0 run          # open TUI dashboard
  $0 restart      # restart everything
EOF
        ;;
esac
