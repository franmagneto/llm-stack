# Open WebUI + llama.cpp Vulkan

O `llama-server` usa o router de modelos com os presets existentes em
`models.ini`. Os modelos iniciam descarregados e sao carregados sob demanda.

## Configuracao

```bash
cp .env.example .env
openssl rand -hex 32
```

Defina o resultado de `openssl rand -hex 32` em `WEBUI_SECRET_KEY` no `.env`.

Crie o `models.ini` que define os presets de modelos para o llama-server:

```bash
cp models.ini.example models.ini
```

Edite-o para ajustar parâmetros como `threads`, `batch-size` e a lista de modelos.
Defina `MODELS_DIR` como o caminho absoluto do diretorio que contem
`models.ini` e o cache dos modelos. Esse diretorio e montado como `/models` e
configurado como `LLAMA_CACHE` no container.

## Iniciar

```bash
podman compose up -d
```

- Open WebUI: `http://localhost:3000`
- API do llama-server: `http://localhost:8080`

O Open WebUI usa a API compativel com OpenAI em `http://llama-server:8080/v1`.

## Gerenciar modelos

```bash
./llama-model.sh list
./llama-model.sh load
./llama-model.sh unload
```

Os comandos `load` e `unload` aceitam outro identificador de modelo como
segundo argumento. Por exemplo:

```bash
./llama-model.sh load unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M
```

## Licença

Este projeto esta sob a [GNU General Public License v3](LICENSE).
