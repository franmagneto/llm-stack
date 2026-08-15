"""Parser para extrair métricas dos logs do llama-server.

Patterns baseados no formato de log do llama.cpp:
  prompt eval time =   1234.56 ms /    50 tokens (  24.69 ms per token,    40.48 tokens per second)
       eval time =    567.89 ms /    10 tokens (  56.79 ms per token,    17.60 tokens per second)
      total time =    1802.45 ms /    60 tokens
n_gen = 0123, tg = 12.34 t/s, tg_3s = 11.87 t/s
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class LogEntry:
    """Uma única entrada de métrica extraída de uma linha de log."""
    type: str = ""  # prompt_tokens, prompt_eval, eval, total, tps
    prompt_tokens: int = 0
    gen_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float | None = None
    tokens: int = 0
    prompt_duration_ms: float | None = None
    gen_duration_ms: float | None = None
    prompt_tps: float | None = None
    gen_tps: float | None = None
    tg_3s: float | None = None
    count: int = 0
    n_gen: int = 0
    is_response: bool = False  # True se vem de linha de resposta (prompt/eval/total time)

    @property
    def gen_tps_avg(self) -> float | None:
        return self.gen_tps

    @property
    def prompt_duration_s(self) -> float | None:
        if self.prompt_duration_ms is not None:
            return self.prompt_duration_ms / 1000.0
        return None

    @property
    def gen_duration_s(self) -> float | None:
        if self.gen_duration_ms is not None:
            return self.gen_duration_ms / 1000.0
        return None


# Regex patterns — ordem importa: prompt eval time vem ANTES do eval time genérico
PROMPT_EVAL_RE = re.compile(
    r'prompt eval time =\s+([\d.]+)\s+ms\s*/\s+(\d+)\s+tokens'
)
EVAL_TIME_RE = re.compile(
    r'eval time =\s+([\d.]+)\s+ms\s*/\s+(\d+)\s+tokens'
)
TOTAL_TIME_RE = re.compile(
    r'total time =\s+([\d.]+)\s+ms\s*/\s+(\d+)\s+tokens'
)
TPS_LINE_RE = re.compile(
    r'n_gen\s*=\s*(\d+),\s*tg\s*=\s*([\d.]+)\s*t/s(?:,\s*tg_3s\s*=\s*([\d.]+)\s*t/s)?'
)
DRAFT_RE = re.compile(
    r'draft acceptance = [\d.]+ \((\d+) accepted / (\d+) generated\)'
)
RESPONSE_START_RE = re.compile(r'processing prompt tokens:\s+(\d+)')


class MetricsAccumulator:
    """Acumula estado entre linhas de log para construir um LogEntry completo.

    As linhas do llama-server vêm em sequências como:
      prompt processing, n_tokens = 50, ...
      prompt eval time = 1234.56 ms / 50 tokens ...
         eval time = 567.89 ms / 10 tokens ...
        total time = 1802.45 ms / 60 tokens
      n_gen = 0123, tg = 12.34 t/s, tg_3s = 11.87 t/s   (durante geração)
    """

    def __init__(self):
        # Última resposta completa
        self._last_entry: LogEntry | None = None
        # Prompt tokens durante processamento
        self._prompt_tokens: int = 0
        # Temporário para prompt tokens
        self._accumulated_prompt_tokens: int = 0
        self._accumulated_gen_tokens: int = 0
        self._accumulated_total_tokens: int = 0
        self.reset()

    def reset(self):
        self.prompt_duration_ms: float | None = None
        self.gen_duration_ms: float | None = None
        self.prompt_tokens: int = 0
        self.gen_tokens: int = 0
        self.total_tokens: int = 0
        self.prompt_tps: float | None = None
        self.gen_tps: float | None = None
        self.tg_3s: float | None = None

    def process_line(self, line: str) -> LogEntry | None:
        """Processa uma linha de log. Retorna LogEntry quando uma resposta completa é detectada."""
        stripped = line.strip()

        # Line: "processing prompt tokens: N" — inicia nova resposta
        m = RESPONSE_START_RE.search(stripped)
        if m:
            self._accumulated_prompt_tokens = int(m.group(1))
            # Retorna LogEntry para tracking de prompt_tokens
            return LogEntry(
                type="prompt_tokens",
                count=int(m.group(1)),
            )

        # Line: "prompt eval time = ..."
        m = PROMPT_EVAL_RE.search(stripped)
        if m:
            self.prompt_duration_ms = float(m.group(1))
            prompt_token_count = int(m.group(2))
            self.prompt_tokens = prompt_token_count
            # Extrair prompt TPS das parenteses se presentes
            # "(  24.69 ms per token,    40.48 tokens per second)"
            tps_match = re.search(r'(\d+\.\d+)\s+tokens per second', stripped)
            if tps_match:
                self.prompt_tps = float(tps_match.group(1))
            return LogEntry(
                type="prompt_eval",
                prompt_tokens=prompt_token_count,
                prompt_duration_ms=self.prompt_duration_ms,
                prompt_tps=self.prompt_tps,
                is_response=True,
            )

        # Line: "   eval time = ..." (gen tokens)
        m = EVAL_TIME_RE.search(stripped)
        if m:
            self.gen_duration_ms = float(m.group(1))
            self.gen_tokens = int(m.group(2))
            return LogEntry(
                type="eval",
                gen_tokens=int(m.group(2)),
                gen_duration_ms=float(m.group(1)),
                is_response=True,
            )

        # Line: "  total time = ..."
        m = TOTAL_TIME_RE.search(stripped)
        if m:
            total_duration_ms = float(m.group(1))
            total_token_count = int(m.group(2))
            # Se gen_duration ainda não foi setado, deriva de total - prompt
            if self.gen_duration_ms is None and self.prompt_duration_ms is not None:
                self.gen_duration_ms = total_duration_ms - self.prompt_duration_ms
            # Se gen_tokens ainda não foi setado, deriva de total - prompt
            if self.gen_tokens == 0:
                self.gen_tokens = max(total_token_count - self.prompt_tokens, 0)
            self.total_tokens = total_token_count

            # Construir e limpar o último LogEntry
            # Usa _accumulated_prompt_tokens se prompt_tokens não foi capturado
            actual_prompt_tokens = self._accumulated_prompt_tokens if self._accumulated_prompt_tokens > 0 else self.prompt_tokens
            actual_gen_tokens = max(total_token_count - actual_prompt_tokens, 0) if self.gen_tokens == 0 else self.gen_tokens

            entry = LogEntry(
                type="total",
                prompt_tokens=actual_prompt_tokens,
                gen_tokens=actual_gen_tokens,
                total_tokens=self.total_tokens,
                prompt_duration_ms=self.prompt_duration_ms,
                gen_duration_ms=self.gen_duration_ms,
                prompt_tps=self.prompt_tps,
                gen_tps=self.gen_tps,
                is_response=True,
            )
            self.reset()
            return entry

        # Line: "n_gen = N, tg = X t/s, ..." (durante geração)
        m = TPS_LINE_RE.search(stripped)
        if m:
            self.gen_tps = float(m.group(2))
            self.tg_3s = float(m.group(3)) if m.group(3) else None
            return LogEntry(
                type="tps",
                gen_tps=self.gen_tps,
                tg_3s=self.tg_3s,
                n_gen=int(m.group(1)),
            )

        return None

    @property
    def last_entry(self) -> LogEntry | None:
        return self._last_entry

    def get_latest(self) -> LogEntry | None:
        """Retorna a última entrada completa ou None."""
        return self._last_entry


def parse_log_line(line: str) -> LogEntry | None:
    """Parseia uma única linha de log, retorna LogEntry ou None."""
    acc = MetricsAccumulator()
    return acc.process_line(line)


def parse_log_text(lines: list[str]) -> list[LogEntry]:
    """Parseia um bloco de linhas de log. Retorna lista de LogEntry completos."""
    acc = MetricsAccumulator()
    entries = []
    for line in lines:
        result = acc.process_line(line)
        if result is not None:
            entries.append(result)
    return entries


def get_prompt_tps_from_entry(entry: LogEntry | None) -> float | None:
    """Extrai prompt TPS de um LogEntry."""
    if entry and entry.is_response:
        return entry.prompt_tps
    return None
