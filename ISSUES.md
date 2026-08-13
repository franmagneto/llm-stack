# Issues

## llama.cpp `/metrics` endpoint returns 400 error
- **Status**: ✅ RESOLVIDO
- **Descrição original**: O endpoint `/metrics` do llama.cpp retornava 400 com a mensagem "model name is missing from the request"
- **Causa**: O endpoint /metrics do proxy llama-server (porta 8080) exige o parâmetro `?model=<id>` para saber qual modelo interno consultar
- **Solução**: Adicionado `_get_model_param()` no TUI que appenda `?model=...` à URL. Também suporta variável `LLAMA_MODEL` para customização
- **Notas**: Todos os metrics agora funcionam corretamente: prompt_tps, gen_tps, cache hit rate (spec_decode acceptance), timestamps, etc.

## TUI containerização para distribuição standalone
- **Status**: Next Step
- **Descrição**: Empacotar a TUI de métricas em um container para distribuição sem dependências locais
- **Branch alvo**: `feature/llama-metrics-container` (ainda não criada)
- **Arquivos planejados**:
  - `llama_metrics/Containerfile` — build neutro (podman/docker)
  - `metrics.sh` — script para construir e rodar o container sob demanda
  - `llama_metrics/.dockerignore` — exclui `.venv/`, `__pycache__/`, `.git/`
- **Arquitetura**: Container rodando sob demanda, sem persistência, sem entrar na stack principal
- **Fluxo do usuário**: `./metrics.sh` → container construído, TUI aberta, 'q' → container destruído
- **Notas**: Merge de `feature/llama-metrics-tui` → `main` já feito. Containerização em branch separada.
