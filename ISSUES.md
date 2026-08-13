# Issues

## llama.cpp `/metrics` endpoint returns 400 error
- **Status**: Open
- **Description**: O endpoint `/metrics` do llama.cpp retorna `{"error":{"code":400,"message":"model name is missing from the request","type":"invalid_request_error"}}` mesmo com o flag `--metrics` presente no comando.
- **Impact**: A TUI (e qualquer scraper Prometheus) não consegue coletar métricas.
- **Workaround**: 
  1. Configurar a variável de ambiente `LLAMA_ARG_ENDPOINT_METRICS=true` no serviço `llama-server` do compose.yaml
  2. Tentar reiniciar o container com `podman compose up -d --force-recreate llama-server` após aplicar a variável
- **Notas**: A imagem `ghcr.io/ggml-org/llama.cpp:server-vulkan` pode estar usando uma versão onde o flag `--metrics` não foi integralmente implementado ou requer configuração adicional.
