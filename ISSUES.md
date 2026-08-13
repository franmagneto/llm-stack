# Issues

## llama.cpp `/metrics` endpoint returns 400 error
- **Status**: ✅ RESOLVIDO
- **Descrição original**: O endpoint `/metrics` do llama.cpp retornava 400 com a mensagem "model name is missing from the request"
- **Causa**: O endpoint /metrics do proxy llama-server (porta 8080) exige o parâmetro `?model=<id>` para saber qual modelo interno consultar
- **Solução**: Adicionado `_get_model_param()` no TUI que appenda `?model=...` à URL. Também suporta variável `LLAMA_MODEL` para customização
- **Notas**: Todos os metrics agora funcionam corretamente: prompt_tps, gen_tps, cache hit rate (spec_decode acceptance), timestamps, etc.
