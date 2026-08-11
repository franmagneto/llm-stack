# AGENTS.md — Open WebUI + llama.cpp Vulkan

## O que ler primeiro

- `compose.yaml` — infra local (llama-server Vulkan + Open WebUI)
- `.env.example` — variáveis de ambiente obrigatórias
- `llama-model.sh` — CLI para gerenciar modelos sob demanda
- `README.md` — instruções de uso

## Stack

Podman Compose · `ghcr.io/ggml-org/llama.cpp:server-vulkan` · `ghcr.io/open-webui/open-webui:main-slim`

## Git

Branch ativa: `develop`. `initial` = branch da especificação.

Fluxo: `git checkout -b feature/<nome> develop` → commits → `git rebase develop` → `git checkout develop && git merge feature/<nome> --no-ff` → `git branch -d feature/<nome>`

Commits: **Conventional Commits** (`feat(scope): description`).

**Regras de commit:**
- **Commit após cada mudança lógica independente** (não espere todos os arquivos estarem prontos)
- **Nunca agrupar múltiplas features/issues em um único commit**
- Exemplo: editar `foo.ts` → commit; editar `bar.ts` → commit; corrigir teste → commit
- Um commit = uma única mudança coerente (uma feature, um fix, uma refactor, um teste)

## Gerenciamento de Issues

- Problemas encontrados devem ser adicionados a `ISSUES.md` se não estiverem listados
- Se o problema já existe na issue, atualizá-la com informações novas
- Após resolver, marcar a issue com ✅ RESOLVIDO e descrever o que foi feito

## Infra local

```bash
podman compose up -d    # sobe llama-server + Open WebUI
podman compose down     # para
podman compose down -v  # para + remove volumes
```

- Open WebUI: `http://localhost:3000`
- API llama-server: `http://localhost:8080`

## Gerenciar modelos

Os modelos iniciam descarregados e carregam sob demanda:

```bash
./llama-model.sh list              # lista todos os modelos (unloaded / loaded)
./llama-model.sh load              # carrega o modelo default (Qwen3.6-35B)
./llama-model.sh unload            # descarrega o modelo default
./llama-model.sh load <id_modelo>  # carrega modelo específico
```

Variáveis de ambiente opcionais:
- `LLAMA_SERVER_URL` — altera a URL do servidor (default `http://localhost:8080`)
- `LLAMA_MODEL` — modelo default usado por `load`/`unload`

## Status de Implementação

✅ **Compose** — llama-server Vulkan com `--no-models-autoload` + Open WebUI via API OpenAI
✅ **CLI** — `llama-model.sh` (bash + curl + jq) para `list`, `load`, `unload`
✅ **Config** — `LLAMA_CACHE=/models`, `MODELS_DIR` obrigatório via `.env`
✅ **Docs** — `.env.example` e `README.md` atualizados
✅ **Validação** — `podman compose config` passa; CLI funciona contra container Vulkan

## Notas técnicas

- Router usa `--models-preset /models/models.ini` para carregar presets de `models.ini`
- `--no-models-autoload` impede carregamento automático; modelo default pode ser explicitamente marcado com `auto-load-model = true` no preset para iniciar carregado
- Open WebUI conecta via API compatível com OpenAI em `http://llama-server:8080/v1`
- `ENABLE_OLLAMA_API=false` desabilita o backend Ollama integrado

## Próximos Passos

1. Testar carregamento/descarregamento com o modelo default em produção
2. Experimentar `auto-load-model = true` se desejar modelo pronto ao iniciar
3. Adicionarhealth check ao llama-server
