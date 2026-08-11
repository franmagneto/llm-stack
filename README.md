# Open WebUI + llama.cpp Vulkan

O `llama-server` usa o router de modelos com os presets existentes em
`models.ini`. Os modelos iniciam descarregados e sao carregados sob demanda.

## Configuracao

```bash
cp .env.example .env
openssl rand -hex 32
```

Defina o resultado de `openssl rand -hex 32` em `WEBUI_SECRET_KEY` no `.env`.

Defina `MODELS_DIR` como o caminho absoluto do diretorio que contem seus
modelos e o arquivo `models.ini` (copie de `models.ini.example`). Esse
diretorio e montado como `/models` no container e configurado como
`LLAMA_CACHE` para onde os modelos sao baixados.

## Baixar modelos

Nao ha um metodo unico — cada repo do HuggingFace tem arquivos
diferentes (GGUF, mmproj, LoRA, etc.). Escolha o que for mais
conveniente.

### llama-server (adaptado)

⚠️ **Este metodo e adaptado** — o `llama-server` nao foi projetado para
download direto. Ele baixa o modelo E O CARREGA após o download.

```bash
podman run --rm -v "$MODELS_DIR:/models:rw" \
  ghcr.io/ggml-org/llama.cpp:server-vulkan \
  --ngl 0 -hf unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M
```

Após baixar, o server inicializa o modelo em memoria. Use `--ngl 0` para
evitar consumo de VRAM da GPU (recomendado se Open Webui estiver ativo).
Adicionar `--hft <token>` para repos gated ou configurar `HF_TOKEN` no
ambiente. O `mmproj` eh baixado automaticamente quando existe no repo.

### Download manual via HuggingFace

Acesse a pagina do repo no HuggingFace, navegue em
`Files and versions` e baixe manualmente o `.gguf` e o `mmproj*.gguf`
(se aplicavel). Util quando quer escolher uma quantizacao exata ou
arquivos que nao seguem o padrao de tag.

### huggingface-cli (Python)

Apos `pip install huggingface_hub`:

```bash
huggingface-cli download unsloth/Qwen3.6-35B-A3B-MTP-GGUF \
  --include "*.gguf" --local-dir $MODELS_DIR
```

Repos gated: o token eh lido automaticamente de `~/.cache/huggingface/token`
se voce ja esta logado com `huggingface-cli login`.

### curl direto (automatizacao)

Para scripts, resolva o nome do arquivo via HF API e baixe diretamente:

```bash
repo_id="unsloth/Qwen3.6-35B-A3B-MTP-GGUF"
filename=$(curl -sf "https://huggingface.co/api/models/$repo_id" \
  | jq -r '.files[].path' | grep -i "Q4_K_M" | head -n1)
curl -L "https://huggingface.co/$repo_id/resolve/main/$filename" \
  -o "$MODELS_DIR/$filename"
```

Para mmproj, repetir com `grep -i "mmproj"` no lugar de `grep -i "Q4_K_M"`.
Repos gated: adicionar `-H "Authorization: Bearer $HF_TOKEN"` ao curl.

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
