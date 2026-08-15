# Open WebUI + llama.cpp Vulkan

O `llama-server` usa o router de modelos com os presets existentes em
`models.ini`. Os modelos iniciam descarregados e são carregados sob demanda.

## Configuração

```bash
cp .env.example .env
openssl rand -hex 32
```

Defina o resultado de `openssl rand -hex 32` em `WEBUI_SECRET_KEY` no `.env`.

Defina `MODELS_DIR` como o caminho absoluto do diretório que contém seus
modelos e o arquivo `models.ini` (copie de `models.ini.example`). Esse
diretório é montado como `/models` no container e configurado como
`LLAMA_CACHE` para onde os modelos são baixados.

## Baixar modelos

Não há um método único — cada repositório do HuggingFace tem arquivos
diferentes (GGUF, mmproj, LoRA, etc.). Escolha o que for mais
conveniente.

### llama-server (adaptado)

⚠️ **Este método é adaptado** — o `llama-server` não foi projetado para
download direto. Ele baixa o modelo E O CARREGA após o download.

```bash
podman run --rm -v "$MODELS_DIR:/models:rw" \
  ghcr.io/ggml-org/llama.cpp:server-vulkan \
  --ngl 0 -hf unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M
```

Após baixar, o server inicializa o modelo em memória. Use `--ngl 0` para
evitar consumo de VRAM da GPU (recomendado se Open WebUI estiver ativo).
Adicionar `--hft <token>` para repositórios gated ou configurar `HF_TOKEN` no
ambiente. O `mmproj` é baixado automaticamente quando existe no repositório.

### Download manual via HuggingFace

Acesse a página do repositório no HuggingFace, navegue em
`Files and versions` e baixe manualmente o `.gguf` e o `mmproj*.gguf`
(se aplicável). Útil quando quer escolher uma quantização exata ou
arquivos que não seguem o padrão de tag.

### huggingface-cli (Python)

Após `pip install huggingface_hub`:

```bash
huggingface-cli download unsloth/Qwen3.6-35B-A3B-MTP-GGUF \
  --include "*.gguf" --local-dir $MODELS_DIR
```

Repositórios gated: o token é lido automaticamente de `~/.cache/huggingface/token`
se você já está logado com `huggingface-cli login`.

### curl direto (automação)

Para scripts, resolva o nome do arquivo via HF API e baixe diretamente:

```bash
repo_id="unsloth/Qwen3.6-35B-A3B-MTP-GGUF"
filename=$(curl -sf "https://huggingface.co/api/models/$repo_id" \
  | jq -r '.files[].path' | grep -i "Q4_K_M" | head -n1)
curl -L "https://huggingface.co/$repo_id/resolve/main/$filename" \
  -o "$MODELS_DIR/$filename"
```

Para mmproj, repetir com `grep -i "mmproj"` no lugar de `grep -i "Q4_K_M"`.
Repositórios gated: adicionar `-H "Authorization: Bearer $HF_TOKEN"` ao curl.

## Iniciar

```bash
podman compose up -d
```

- Open WebUI: `http://localhost:3000`
- API do llama-server: `http://localhost:8080`

O Open WebUI usa a API compatível com OpenAI em `http://llama-server:8080/v1`.

## Métricas (TUI)

Dashboard em tempo real com tokens/s, latência e throughput do llama-server.
Os dados vêm do log compartilhado (`llama-logs:/var/log/llama`).

```bash
# Iniciar server + webui em background
podman compose up -d

# Abrir TUI de métricas em foreground
podman compose --profile metrics run --rm llama-metrics
```

Fechar com `Ctrl+C`. O server continua rodando em background.

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

Este projeto está sob a [GNU General Public License v3](LICENSE).
