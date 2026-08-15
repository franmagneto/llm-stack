"""Dashboard TUI para métricas do llama.cpp — baseado em logs do servidor."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static, TabbedContent, Tabs

from .log_parser import (
    LogEntry,
    MetricsAccumulator,
)


# Defaults
DEFAULT_MODELS_URL = "http://localhost:8080/models"
POLL_INTERVAL = 3  # seconds — aligned with llama.cpp hardcoded 3s TPS log interval
MAX_HISTORY = 30
DEFAULT_LOG_PATH = "/var/log/llama/server.log"


def _get_model_param() -> str:
    """Retorna o parâmetro de modelo para o endpoint /metrics."""
    model = os.getenv("LLAMA_MODEL")
    if model:
        return f"?model={model}"
    return "?model=unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M"


@dataclass
class ModelStatus:
    id: str = ""
    value: str = "unknown"

    def display(self) -> tuple[str, str]:
        """Returns (icon, text, css_class) for model status."""
        if self.value == "loaded":
            return ("●", f"{self.id}", "value-good")
        elif self.value == "unloading" or self.value == "loading":
            return ("◻", self.value, "value-warning")
        elif self.value == "error":
            return ("✖", "error", "value-slow")
        elif self.value == "unloaded":
            return ("○", "unloaded", "value-slow")
        return ("?", "unknown", "value-slow")


@dataclass
class MetricSnapshot:
    model_status: ModelStatus | None = None
    prompt_tps: float | None = None

    gen_tps: float | None = None

    prompt_tps_avg: float | None = None

    gen_tps_avg: float | None = None

    prompt_duration_ms: float | None = None
    gen_duration_ms: float | None = None
    total_prompt_tokens: int = 0
    total_generated_tokens: int = 0
    total_prompts: int = 0
    total_samples: int = 0
    n_context: int = 0
    raw: dict = field(default_factory=dict)
    _entry: LogEntry | None = field(default=None, repr=False)


class MetricsClient:
    """Busca status do modelo via /models. Métricas vêm do log via LogTailer."""

    def __init__(self, models_url: str | None = None):
        api_base = os.getenv("LLAMA_API_URL", "http://localhost:8080")
        self.models_url = models_url or f"{api_base}/models"
        self._api_base = f"{api_base}/v1"

    def poll_model_status(self) -> ModelStatus:
        """Busca status do modelo via /models."""
        try:
            req = urllib.request.Request(self.models_url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            models = data.get("data", [])
            target_model = _get_model_param().split("=")[-1]

            for m in models:
                if m.get("id") == target_model or any(alias == target_model for alias in m.get("aliases", [])):
                    return ModelStatus(id=m.get("id", ""), value=m.get("status", {}).get("value", "unknown"))

            if models:
                m = models[0]
                return ModelStatus(id=m.get("id", ""), value=m.get("status", {}).get("value", "unknown"))

            return ModelStatus(value="unknown")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError, json.JSONDecodeError):
            return ModelStatus(value="unknown")


class LogTailer:
    """Lê novas linhas do log file do llama-server, mantém posição, parseia métricas."""

    def __init__(self, log_path: str = DEFAULT_LOG_PATH):
        self.log_path = Path(log_path)
        self._position = 0
        self._accumulator = MetricsAccumulator()
        self._buffer: list[str] = []
        self._last_snapshot: MetricSnapshot | None = None

    def _open(self):
        try:
            self._file = open(self.log_path, "r", encoding="utf-8", errors="replace")
            self._file.seek(self._position)
            self._is_open = True
        except (FileNotFoundError, PermissionError, OSError):
            self._is_open = False

    def _close(self):
        if hasattr(self, '_file') and self._is_open:
            try:
                self._file.close()
            except OSError:
                pass
            self._is_open = False

    def _read_new_lines(self) -> list[str]:
        """Leia novas linhas desde a última posição."""
        if not hasattr(self, '_file') or not self._is_open:
            self._open()
            if not self._is_open:
                return []

        lines = []
        while True:
            line = self._file.readline()
            if not line:
                break
            lines.append(line)
            self._position = self._file.tell()
        return lines

    def poll(self) -> MetricSnapshot | None:
        """Lê novas linhas do log, parseia, retorna MetricSnapshot com última entrada completa."""
        model_status = MetricsClient().poll_model_status()

        lines = self._read_new_lines()
        if not lines:
            if self._last_snapshot:
                self._last_snapshot.model_status = model_status
                return self._last_snapshot
            return MetricSnapshot(model_status=model_status)

        # Processar linhas no accumulator para construir LogEntry completo
        response_entry = None
        for line in lines:
            result = self._accumulator.process_line(line)
            if result is not None and result.type == "total":
                response_entry = result

        if response_entry:
            self._last_snapshot = MetricSnapshot(
                model_status=model_status,
                prompt_tps=response_entry.prompt_tps,
                gen_tps=response_entry.gen_tps,
                prompt_duration_ms=response_entry.prompt_duration_ms,
                gen_duration_ms=response_entry.gen_duration_ms,
                total_prompt_tokens=response_entry.prompt_tokens,
                total_generated_tokens=response_entry.gen_tokens,
                total_prompts=response_entry.prompt_tokens,
                total_samples=response_entry.gen_tokens,
                n_context=0,
                gen_tps_avg=response_entry.gen_tps,
                prompt_tps_avg=response_entry.prompt_tps,
                _entry=response_entry,
            )
            return self._last_snapshot

        # Se não há resposta completa, usa gen_tps atual do acumulador
        if self._last_snapshot:
            self._last_snapshot.model_status = model_status
            self._last_snapshot.prompt_tps = self._accumulator.prompt_tps or self._last_snapshot.prompt_tps
            self._last_snapshot.gen_tps = self._accumulator.gen_tps or self._last_snapshot.gen_tps
            return self._last_snapshot

        self._last_snapshot = MetricSnapshot(
            model_status=model_status,
            prompt_tps=self._accumulator.prompt_tps,
            gen_tps=self._accumulator.gen_tps,
            _entry=None,
        )
        return self._last_snapshot

    def close(self):
        self._close()


class DashboardView(Static):
    """Visualização principal do dashboard."""

    CSS = """
    DashboardView {
        layout: vertical;
        padding: 1;
        width: 100%;
    }

    #model-status {
        background: $boost;
        height: 3;
    }

    .metric-row {
        height: 3;
        border: solid cyan;
        margin-bottom: 1;
        padding: 0 1;
    }

    .metric-title {
        text-align: center;
        color: cyan;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    #inference-tokens {
        background: $boost;
        height: 8;
        margin-top: 1;
    }

    #timing-volume {
        background: $boost;
        min-width: 40;
        height: 12;
        margin-right: 1;
    }

    #throughput {
        background: $boost;
        min-width: 20;
        height: 12;
    }

    .metric-text {
        margin-left: 1;
        max-width: 100%;
    }

    .value-good {
        color: green;
        text-style: bold;
    }

    .value-slow {
        color: red;
        text-style: bold;
    }

    .value-warning {
        color: yellow;
        text-style: bold;
    }

    .status-connected {
        color: $accent;
        text-style: bold;
    }

    .status-disconnected {
        color: red;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="model-status"):
            yield Label("Model", classes="metric-title")
            self._model_label = Label("  ● Loading...", classes="metric-text")
            yield self._model_label

        with Vertical(id="inference-tokens"):
            yield Label("Tokens/s", classes="metric-title")
            self._prompt_label = Label("  Prompt tokens/s:   ---", classes="metric-text")
            self._sample_label = Label("  Gen tokens/s:      ---", classes="metric-text")
            yield self._prompt_label
            yield self._sample_label

        with Horizontal():
            with Vertical(id="timing-volume"):
                yield Label("Timing", classes="metric-title")
                self._prompt_dur = Label("  Prompt duration:   ---", classes="metric-text")
                self._token_dur = Label("  Gen duration:      ---", classes="metric-text")
                self._total_tokens = Label("  Total tokens:      ---", classes="metric-text")
                self._total_prompts = Label("  Total prompts:     ---", classes="metric-text")
                self._total_samples = Label("  Total generated:   ---", classes="metric-text")
                yield self._prompt_dur
                yield self._token_dur
                yield self._total_tokens
                yield self._total_prompts
                yield self._total_samples

            with Vertical(id="throughput"):
                yield Label("Throughput", classes="metric-title")
                self._prompt_tps = Label("  Prompt avg TPS:   ---", classes="metric-text")
                self._gen_tps = Label("  Gen avg TPS:      ---", classes="metric-text")
                yield self._prompt_tps
                yield self._gen_tps

    def update(self, snap: MetricSnapshot | None):
        """Atualiza todos os labels com o snapshot."""
        # Model status always first (before _set_all which resets all labels)
        if snap is None or not snap.model_status:
            self._model_label.update("  Model:   ? unknown")
            self._set_all("---")
            return

        # Model status
        ms = snap.model_status
        if ms:
            icon, text, cls = ms.display()
            if ms.value == "loaded":
                self._model_label.update(f"  Model:   {icon} {ms.id}")
            else:
                self._model_label.update(f"  Model:   {icon} {text}")
            self._model_label.remove_class("value-good", "value-slow", "value-warning")
            self._model_label.add_class(cls)
        else:
            self._model_label.update("  Model:   ? unknown")
            self._model_label.remove_class("value-good", "value-slow", "value-warning")

        pt = snap.prompt_tps
        gt = snap.gen_tps

        self._prompt_label.update(f"  Prompt tokens/s:   {self._fmt(pt, '.1f')}")
        self._sample_label.update(f"  Gen tokens/s:      {self._fmt(gt, '.1f')}")

        # Color coding for TPS
        if pt is not None:
            self._prompt_label.add_class("value-good" if pt > 8 else "value-slow")
        if gt is not None:
            self._sample_label.add_class("value-good" if gt > 0.5 else "value-slow")

        pd = snap.prompt_duration_ms
        td = snap.gen_duration_ms

        self._prompt_dur.update(f"  Prompt duration:   {self._fmt(pd, '5.2f')} s")
        self._token_dur.update(f"  Gen duration:      {self._fmt(td, '5.2f')} s")
        self._total_tokens.update(f"  Total tokens:      {snap.total_prompt_tokens + (snap.total_generated_tokens or 0):>10,}")
        self._total_prompts.update(f"  Total prompts:     {snap.total_prompts:>10,}")
        self._total_samples.update(f"  Total generated:   {snap.total_generated_tokens:>10,}")

        self._prompt_tps.update(f"  Prompt avg TPS:   {self._fmt(snap.prompt_tps_avg, '.1f')}")
        self._gen_tps.update(f"  Gen avg TPS:      {self._fmt(snap.gen_tps_avg, '.1f')}")

    def _fmt(self, val: float | None, fmt: str) -> str:
        if val is None:
            return "---"
        return f"{val:{fmt}}"

    def _set_all(self, val: str):
        for label in [self._prompt_label, self._sample_label,
                        self._prompt_dur, self._token_dur,
                        self._total_tokens, self._total_prompts, self._total_samples,
                         self._prompt_tps, self._gen_tps, self._model_label]:
            parts = label.plain.split(":")
            label_text = f"  {parts[0]}: {val}" if len(parts) > 1 else label.plain
            label.update(label_text)


class HistoryChart(Static):
    """Mini gráfico de linha para histórico de TPS."""

    CSS = """
    HistoryChart {
        background: $boost;
        border: solid cyan;
        padding: 1;
        height: 8;
        width: 100%;
    }

    .chart-title {
        text-align: center;
        color: cyan;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    #chart-canvas {
        width: 100%;
        height: calc(100% - 2);
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("TPS History (30s)", classes="chart-title")
        self._prompt_hist = deque(maxlen=30)
        self._sample_hist = deque(maxlen=30)
        self._canvas = Label("")
        yield self._canvas

    def add_point(self, prompt: float | None, sample: float | None):
        if prompt is not None:
            self._prompt_hist.append(prompt)
        if sample is not None:
            self._sample_hist.append(sample)
        self._draw()

    def _build_lines(self):
        data = [
            ("  Prompt:  ", self._prompt_hist, "cyan"),
            ("  Gen:     ", self._sample_hist, "yellow"),
        ]

        lines = []
        for label, hist, color in data:
            if not hist:
                lines.append(f"{label} -")
                continue
            max_val = max(max(hist), 1)
            bar = "".join(
                "█" if v / max_val > 0.7 else "▓" if v / max_val > 0.4 else "▒" if v / max_val > 0.1 else "░"
                for v in hist
            )
            lines.append(f"{label}{bar} ({hist[-1]:.1f})")

        return "\n".join(lines)

    def _draw(self):
        text = self._build_lines()
        self._canvas.update(text)


class     MainScreen(Screen):
    """Tela principal do dashboard."""

    CSS = """
    MainScreen {
        align: center middle;
        width: 100%;
        height: 100%;
    }

    #header-row {
        height: 3;
        width: 100%;
        dock: top;
        background: #1a1b26;
        border: solid cyan;
    }

    #url-display {
        width: 100%;
        text-align: center;
    }

    #status-display {
        width: 100%;
        text-align: center;
    }

    .generating {
        color: #ffcc00;
        text-style: bold;
    }

    #main-content {
        width: 100%;
        height: 100%;
        margin-top: 2;
        margin-bottom: 1;
    }

    #footer-info {
        dock: bottom;
        height: 3;
        width: 100%;
        padding: 0 2;
        background: #1a1b26;
    }

    #chart-row {
        dock: bottom;
        height: 10;
        width: 100%;
        margin-bottom: 4;
    }

    .hint-text {
        color: #556677;
        text-style: dim;
        margin-left: 1;
    }

    .status-connected {
        color: $accent;
        text-style: bold;
    }

    .status-disconnected {
        color: red;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="header-row"):
            self._url = Label("", id="url-display")
            self._status = Label("", id="status-display")
            yield self._url
            yield self._status

        with Container(id="main-content"):
            yield DashboardView(id="dashboard")
        with Container(id="chart-row"):
            yield HistoryChart(id="chart")

        with Container(id="footer-info"):
            yield Label(
                f"  ▶ Log: /var/log/llama/server.log → podman run --rm -it -v llama-logs:/var/log/llama:ro llama-metrics-tui",
                classes="hint-text",
            )
            yield Label(
                "  ▶ Model env:  LLAMA_MODEL=qwen  podman run -e LLAMA_MODEL=qwen ...",
                classes="hint-text",
            )

        yield Footer()

    def on_mount(self) -> None:
        log_path = os.getenv("LLAMA_LOG_PATH", DEFAULT_LOG_PATH)
        self._client = LogTailer(log_path)
        self._history = []
        self._snapshots = deque(maxlen=POLL_INTERVAL * 2)
        self._set_url_default()
        self._refresh_id = self.set_interval(POLL_INTERVAL, self.refresh_metrics)

    def _set_url_default(self):
        model = _get_model_param().split("=")[-1]
        self._url.update(f"llama.cpp metrics → log: /var/log/llama/server.log")
        self._status.update("● Connecting...")
        self._status.add_class("status-disconnected")

    def get_metrics(self) -> MetricSnapshot | None:
        """Busca uma nova leitura das métricas via log tailer."""
        return self._client.poll()

    watch_metrics = get_metrics

    def refresh_metrics(self):
        """Atualiza o dashboard com nova leitura."""
        if not hasattr(self, '_connect_attempts'):
            self._connect_attempts = 0
        self._connect_attempts += 1

        snap = self.get_metrics()
        dash = self.query_one("#dashboard", DashboardView)
        dash.update(snap)

        if snap:
            chart = self.query_one("#chart", HistoryChart)
            if snap.prompt_tps is not None or snap.gen_tps is not None:
                chart.add_point(snap.prompt_tps, snap.gen_tps)

            self._status.update("● Connected")
            self._status.remove_class("status-disconnected")
            self._status.add_class("status-connected")
            self._history.append(snap)
        else:
            self._status.update("● Disconnected")
            self._status.add_class("status-disconnected")
            self._status.remove_class("status-connected")
            if self._connect_attempts >= POLL_INTERVAL * 2:
                self._status.update(
                    "● Disconnected — check compose.yaml for 'llama-logs' volume"
                )

    def on_key(self, event):
        if event.key == "q":
            event.stop()
            self.app.exit()


class MetricsApp(App):
    """App principal do dashboard TUI."""

    CSS = """
    Screen {
        background: #1a1b26;
        color: #c0caf5;
    }

    Footer {
        background: #1a1b26;
    }
    """

    SCREENS = {"main": MainScreen}

    def on_mount(self) -> None:
        self.push_screen("main")

    def on_key(self, event):
        if event.key == "q":
            self.exit()


def main():
    """Entry point."""
    app = MetricsApp()
    app.run()


if __name__ == "__main__":
    main()
