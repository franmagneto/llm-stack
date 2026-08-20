#!/bin/bash
# Wrapper para llama-server com auto-load sob demanda ativado por padrão.
#
# O modelo é carregado automaticamente na primeira requisição de chat/completion.

set -eu

# Criar diretório de logs compartilhado (volume)
mkdir -p /var/log/llama
LOG_FILE="/var/log/llama/server.log"

# Iniciar llama-server em background com logs redirecionados para arquivo + console
/app/llama-server "$@" >> "$LOG_FILE" 2>&1
