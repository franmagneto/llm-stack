"""Client para fetch/parsear Prometheus metrics do llama.cpp."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class HistogramMetric:
    name: str
    description: str
    help_text: str
    buckets: dict[float, int] = field(default_factory=dict)
    bucket_sum: float = 0.0
    bucket_count: int = 0


@dataclass
class CounterMetric:
    name: str
    description: str
    help_text: str
    value: float = 0.0


@dataclass
class UntypedMetric:
    name: str
    description: str
    help_text: str
    value: float = 0.0


Metrics = dict[str, CounterMetric | HistogramMetric | UntypedMetric]


def parse_prometheus_text(raw: str) -> Metrics:
    """Parseio o formato text/plain do endpoint /metrics do llama.cpp.

    Agregacao simples: somamos valores de contadores com labels
    (ex. llama_prompt_tokens_total{id="0",v="0"} + ... = total).
    Histo gramas sao parseiados separadamente (_bucket, _count, _sum).
    """
    metrics: Metrics = {}
    current_type: str = ""
    last_type_time: int = 0
    last_ts: int = 0

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("# HELP "):
            continue
        elif line.startswith("# TYPE "):
            parts = line.split()
            current_type = parts[3] if len(parts) > 3 else ""
            last_type_time = _now_seconds()
        elif line.startswith("#"):
            continue
        elif line and current_type:
            value_str, ts = _parse_metric_value(line)
            if value_str is None:
                continue
            ts = max(ts, _now_seconds())

            # Reset type if gap > 3s (new metric block started)
            if ts - last_type_time > 3:
                current_type = ""
                continue

            name = _extract_name(line, "")
            if current_type in ("counter", "gauge"):
                _handle_counter(metrics, name, value_str)
            elif current_type == "histogram":
                _handle_histogram_value(metrics, name, value_str, line)

    return metrics


def _parse_metric_value(line: str) -> tuple[float | None, int]:
    """Retorna (valor, timestamp) de uma linha de métrica."""
    parts = line.split()
    if not parts:
        return None, 0

    ts = 0
    try:
        # Formato com timestamp: <name>{...} <value> <timestamp_ms>
        if len(parts) >= 3:
            val = float(parts[1])
            ts = int(parts[2])
            return val, ts
        # Formato com labels: <name>{...} <value>
        if len(parts) == 2:
            return float(parts[1]), 0
    except (ValueError, IndexError):
        pass

    return None, ts


def _extract_name(line: str, _fallback: str) -> str:
    """Extrai o nome da métrica de uma linha prometheus."""
    import re
    # Remove labels {key="val",...} e pega a parte antes
    match = re.match(r'([a-zA-Z_:][a-zA-Z0-9_:]*)', line)
    if not match:
        return _fallback
    base = match.group(1)

    # Para histogramas, mantemos o nome completo para evitar
    # que _count, _sum e _bucket se fundam com contadores
    if base.endswith("_bucket") or base.endswith("_sum") or base.endswith("_count"):
        return base
    # Remove histogram suffixes para contadores normais
    if base.endswith("_pred"):
        pass  # keeping _pred as is
    return base


def _handle_counter(metrics: Metrics, name: str, value_str: str):
    """Acumula valores de contadores com labels (soma todas as labels)."""
    if name not in metrics:
        metrics[name] = CounterMetric(name=name, description="", help_text="")
    m = metrics[name]
    if isinstance(m, CounterMetric):
        m.value += float(value_str)


def _handle_histogram_value(metrics: Metrics, name: str, value_str: str, original_line: str = ""):
    """Lida com valores de histograma (_bucket, _sum, _count)."""
    # Strip suffixes to get the histogram base name
    base_name = name
    suffix = None
    if name.endswith("_count"):
        base_name = name[:-6]
        suffix = "_count"
    elif name.endswith("_sum"):
        base_name = name[:-4]
        suffix = "_sum"
    elif name.endswith("_bucket"):
        base_name = name[:-7]
        suffix = "_bucket"

    # Create histogram if not exists
    if base_name not in metrics:
        metrics[base_name] = HistogramMetric(name=base_name, description="", help_text="")
    h = metrics[base_name]

    if suffix == "_bucket":
        # Extract le= value — need original line (name is already stripped of suffix)
        line_for_le = original_line if original_line else name
        import re
        match = re.search(r'le="([^"]+)"', line_for_le)
        if not match:
            return
        try:
            upper = float(match.group(1))
        except ValueError:
            return
        h.buckets[upper] = float(value_str)
    elif suffix == "_sum":
        h.bucket_sum = float(value_str)
    elif suffix == "_count":
        h.bucket_count = float(value_str)


def _now_seconds() -> int:
    return int(time.time())


# ============================================================================
# Métricas derivadas — nomes reais do llama.cpp prometheus output
# ============================================================================

# Mapeamento nome real → descritivo
_METRIC_MAP = {
    "llamacpp:prompt_tokens_total": "prompt_tokens",
    "llamacpp:token_cache": "cached_tokens",
    "llamacpp:token_pred": "predicted_tokens",
    "llamacpp:n_context": "active_contexts",
    "llamacpp:n_prompt": "prompt_count",
    "llamacpp:prompt_duration_total": "prompt_duration_total",
    "llamacpp:token_duration_total": "token_duration_total",
}


def _sum_metric(metrics: Metrics, base_name: str) -> float:
    """Busca valor de um contador (já agregado pelo parser)."""
    val = metrics.get(base_name)
    if isinstance(val, CounterMetric):
        return val.value
    return None


def _sum_all_metrics(metrics: Metrics, prefix: str) -> float:
    """Soma todos os contadores que começam com o prefixo."""
    total = 0.0
    for key, val in metrics.items():
        if key.startswith(prefix) and isinstance(val, CounterMetric):
            total += val.value
    return total if total else None


def get_context_tps(metrics: Metrics) -> float | None:
    """Tokens per segundo processados no contexto (prompt)."""
    val = metrics.get("llamacpp:prompt_seconds_total")
    total_tokens = _sum_metric(metrics, "llamacpp:prompt_tokens_total")
    if val and isinstance(val, CounterMetric) and val.value > 0 and total_tokens:
        return total_tokens / val.value
    return None







def get_sampling_tps(metrics: Metrics) -> float | None:
    """Tokens per segundo amostrados (tokens gerados por segundo)."""
    val = metrics.get("llamacpp:tokens_predicted_seconds_total")
    total_tokens = _sum_metric(metrics, "llamacpp:tokens_predicted_total")
    if val and isinstance(val, CounterMetric) and val.value > 0 and total_tokens:
        return total_tokens / val.value
    return None


def get_prompt_duration_s(metrics: Metrics) -> float | None:
    """Tempo total de processamento do prompt (segundos)."""
    val = metrics.get("llamacpp:prompt_seconds_total")
    if isinstance(val, CounterMetric):
        return val.value
    return None


def get_gen_duration_s(metrics: Metrics) -> float | None:
    """Tempo total de token generation (segundos)."""
    val = metrics.get("llamacpp:tokens_predicted_seconds_total")
    if isinstance(val, CounterMetric):
        return val.value
    return None


def get_total_prompt_tokens(metrics: Metrics) -> int:
    """Total de tokens processados no prompt."""
    return int(_sum_metric(metrics, "llamacpp:prompt_tokens_total") or 0)


def get_total_tokens(metrics: Metrics) -> int:
    """Total de tokens (prompt + geração)."""
    prompt = _sum_metric(metrics, "llamacpp:prompt_tokens_total") or 0
    pred = _sum_metric(metrics, "llamacpp:tokens_predicted_total") or 0
    return int(prompt + pred)


def get_n_prompt(metrics: Metrics) -> int:
    """Total de requisições de prompt (completions)."""
    val = metrics.get("llamacpp:n_decode_total")
    if isinstance(val, CounterMetric):
        return int(val.value)
    return 0


def get_n_pred(metrics: Metrics) -> int:
    """Total de tokens gerados."""
    return int(_sum_metric(metrics, "llamacpp:tokens_predicted_total") or 0)


def get_n_tokens_cached(metrics: Metrics) -> int:
    """Tokens aceitos no spec decode (draft acceptance)."""
    return int(_sum_metric(metrics, "llamacpp:spec_decode_num_accepted_tokens_total") or 0)


def get_cache_hit_pct(metrics: Metrics) -> float | None:
    """Taxa de aceitação de drafts (cache hit aproximado para MTP)."""
    accepted = _sum_metric(metrics, "llamacpp:spec_decode_num_accepted_tokens_total") or 0
    drafts = _sum_metric(metrics, "llamacpp:spec_decode_num_draft_tokens_total") or 0
    if drafts == 0:
        return None
    return accepted / drafts * 100


def get_n_tokens_pred(metrics: Metrics) -> int:
    """Tokens previstos (spec decode generated)."""
    return int(_sum_metric(metrics, "llamacpp:spec_decode_num_draft_tokens_total") or 0)


def get_n_context(metrics: Metrics) -> int:
    """Número atual de contextos ativos."""
    val = metrics.get("llamacpp:n_tokens_max")
    if isinstance(val, CounterMetric):
        return int(val.value)
    return 0


def get_prompt_tokens_seconds_p50(metrics: Metrics) -> float | None:
    """Valor atual do gauge prompt_tokens_seconds (tps mediano aproximado)."""
    val = metrics.get("llamacpp:prompt_tokens_seconds")
    if isinstance(val, UntypedMetric) and val.value > 0:
        return val.value
    return None


def get_generation_tokens_seconds_p50(metrics: Metrics) -> float | None:
    """Valor atual do gauge predicted_tokens_seconds (tps mediano aproximado)."""
    val = metrics.get("llamacpp:predicted_tokens_seconds")
    if isinstance(val, UntypedMetric) and val.value > 0:
        return val.value
    return None


def _histogram_percentile(h: HistogramMetric, p: float) -> float | None:
    """Calcula percentil aproximado de um histograma."""
    if not h.buckets or h.bucket_count <= 0:
        return None
    sorted_bounds = sorted(h.buckets.keys())
    target = (p / 100) * h.bucket_count
    for i, bound in enumerate(sorted_bounds):
        count = h.buckets[bound]
        if count >= target:
            if i > 0:
                prev_bound = sorted_bounds[i - 1]
                prev_count = h.buckets[prev_bound]
                if count > prev_count:
                    frac = (target - prev_count) / (count - prev_count)
                    return prev_bound + frac * (bound - prev_bound)
            return bound
    return sorted_bounds[-1]
