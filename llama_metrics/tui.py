"""Dashboard TUI para métricas do llama.cpp."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static, TabbedContent, Tabs


# Defaults
DEFAULT_URL = "http://localhost:8080/metrics"
POLL_INTERVAL = 2  # seconds
MAX_HISTORY = 30


def _get_model_param() -> str:
    """Retorna o parâmetro de modelo para o endpoint /metrics."""
    import os
    model = os.getenv("LLAMA_MODEL")
    if model:
        return f"?model={model}"
    return "?model=unsloth/Qwen3.6-35B-A3B-MTP-GGUF:Q4_K_M"


@dataclass
class MetricSnapshot:
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
    n_tokens_cached: int = 0
    n_tokens_pred: int = 0
    n_context: int = 0
    pct_cached: float | None = None

    raw: dict = field(default_factory=dict)


class MetricsClient:
    """Busca e parseia métricas do llama.cpp via /metrics."""

    def __init__(self, url: str = DEFAULT_URL):
        self.url = url
        self.raw_data: dict = {}

    def poll(self) -> MetricSnapshot | None:
        try:
            url = f"{self.url}{_get_model_param()}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                raw = resp.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return None

        from client import (
            parse_prometheus_text,
            get_context_tps,
            get_sampling_tps,
            get_prompt_duration_s,
            get_gen_duration_s,
            get_total_prompt_tokens,
            get_n_prompt,
            get_n_pred,
            get_n_tokens_cached,
            get_n_tokens_pred,
            get_n_context,
            get_prompt_tps,
            get_gen_tps,
            get_cache_hit_pct,
        )

        metrics = parse_prometheus_text(raw) or {}
        self.raw_data = {k: v.value if hasattr(v, "value") else str(v) for k, v in metrics.items()}

        pct_cached = get_cache_hit_pct(metrics)

        return MetricSnapshot(
            prompt_tps=get_prompt_tps(metrics),
            gen_tps=get_gen_tps(metrics),
            prompt_duration_ms=get_prompt_duration_s(metrics),
            gen_duration_ms=get_gen_duration_s(metrics),
            total_prompt_tokens=get_total_prompt_tokens(metrics),
            total_generated_tokens=get_n_pred(metrics),
            total_prompts=get_n_prompt(metrics),
            total_samples=get_n_pred(metrics),
            n_tokens_cached=get_n_tokens_cached(metrics),
            n_tokens_pred=get_n_tokens_pred(metrics),
            n_context=get_n_context(metrics),
            pct_cached=pct_cached,
            prompt_tps_avg=get_context_tps(metrics),
            gen_tps_avg=get_sampling_tps(metrics),
            raw=metrics,
        )


class MetricBar(Static):
    """Barra visual de métrica: label + barra + valor."""

    def __init__(self, label: str, value_fmt: str = "", bar_width: int = 20):
        self._label = label
        self._value_fmt = value_fmt
        self._bar_width = bar_width
        super().__init__()

    def update_display(self, value: float | None, max_value: float | None = None):
        if value is None:
            self.update(f"{self._label}: {'---':>12}")
            return

        formatted = f"{value:>{self._bar_width}.{self._value_fmt}}" if self._value_fmt else f"{value!s:>{self._bar_width}}"
        self.update(f"{self._label}: {formatted}")


class DashboardView(Static):
    """Visualização principal do dashboard."""

    CSS = """
    DashboardView {
        layout: vertical;
        padding: 1;
        width: 100%;
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
        height: 12;
    }

    #timing-volume {
        background: $boost;
        min-width: 40;
        height: 15;
        margin-right: 1;
    }

    #throughput {
        background: $boost;
        min-width: 20;
        height: 15;
    }

    #cache-info {
        background: $boost;
        margin-top: 1;
        height: 3;
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
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="inference-tokens"):
            yield Label("Tokens/s", classes="metric-title")
            self._prompt_label = Label("  Prompt tokens/s:  ---", classes="metric-text")
            self._cache_label = Label("  Cache hit ratio:   ---", classes="metric-text")
            self._sample_label = Label("  Gen tokens/s:      ---", classes="metric-text")
            yield self._prompt_label
            yield self._cache_label
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

        with Vertical(id="cache-info"):
            yield Label("Cache & Context", classes="metric-title")
            self._cached = Label("  Cached tokens:  ---", classes="metric-text")
            self._pred = Label("  Predicted:      ---", classes="metric-text")
            self._active_ctx = Label("  Active contexts: ---", classes="metric-text")
            yield self._cached
            yield self._pred
            yield self._active_ctx

    def update(self, snap: MetricSnapshot | None):
        """Atualiza todos os labels com o snapshot."""
        if snap is None:
            self._set_all("---")
            return

        pt = snap.prompt_tps
        ct = snap.pct_cached
        gt = snap.gen_tps

        self._prompt_label.update(f"  Prompt tokens/s:   {self._fmt(pt, '.1f')}")
        self._cache_label.update(f"  Cache hit ratio:   {self._fmt(ct, '.1f') if ct is not None else '---'} %")
        self._sample_label.update(f"  Gen tokens/s:      {self._fmt(gt, '.4f')}")

        # Color coding for TPS
        self._prompt_label.add_class("value-good" if (pt and pt > 8) else "value-slow" if pt and pt < 3 else "")
        self._sample_label.add_class("value-good" if (gt and gt > 0.5) else "value-slow" if gt and gt < 0.1 else "")

        pd = snap.prompt_duration_ms
        td = snap.gen_duration_ms

        self._prompt_dur.update(f"  Prompt duration:   {self._fmt(pd, '5.2f')} s")
        self._token_dur.update(f"  Gen duration:      {self._fmt(td, '5.2f')} s")
        self._total_tokens.update(f"  Total tokens:      {snap.total_prompt_tokens + (snap.total_generated_tokens or 0):>10,}")
        self._total_prompts.update(f"  Total prompts:     {snap.total_prompts:>10,}")
        self._total_samples.update(f"  Total generated:   {snap.total_generated_tokens:>10,}")

        self._prompt_tps.update(f"  Prompt avg TPS:   {self._fmt(snap.prompt_tps_avg, '.1f')}")
        self._gen_tps.update(f"  Gen avg TPS:      {self._fmt(snap.gen_tps_avg, '.1f')}")

        self._cached.update(f"  Cached tokens:   {snap.n_tokens_cached:>10,}")
        self._pred.update(f"  Predicted:        {snap.n_tokens_pred:>10,}")
        self._active_ctx.update(f"  Active contexts: {snap.n_context:>10,}")

    def _fmt(self, val: float | None, fmt: str) -> str:
        if val is None:
            return "---"
        return f"{val:{fmt}}"

    def _set_all(self, val: str):
        for label in [self._prompt_label, self._cache_label, self._sample_label,
                      self._prompt_dur, self._token_dur,
                      self._total_tokens, self._total_prompts, self._total_samples,
                       self._prompt_tps, self._gen_tps,
                      self._cached, self._pred, self._active_ctx]:
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
        self._cache_hist = deque(maxlen=30)
        self._sample_hist = deque(maxlen=30)
        self._canvas = Label("")
        yield self._canvas

    def add_point(self, prompt: float | None, cached: float | None, sample: float | None):
        if prompt is not None:
            self._prompt_hist.append(prompt)
        if cached is not None:
            self._cache_hist.append(cached)
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

    #main-content {
        width: 100%;
        height: 100%;
        margin-top: 1;
        margin-bottom: 1;
    }

    #footer-info {
        dock: bottom;
        height: 4;
        width: 100%;
        padding: 0 2;
        background: #1a1b26;
    }

    #chart-row {
        dock: bottom;
        height: 10;
        width: 100%;
        margin-bottom: 5;
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
        with Container(id="header-row"):
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
                "  ▶  Run:  podman run --rm -it --network host llama-metrics-tui",
                classes="hint-text",
            )
            yield Label(
                "  ▶  Model env:  LLAMA_MODEL=qwen  podman run -e LLAMA_MODEL=qwen ...",
                classes="hint-text",
            )
            yield Label(
                "  Press q or Ctrl + D to exit",
                classes="hint-text",
            )

        yield Footer()

    def on_mount(self) -> None:
        self._client = MetricsClient()
        self._history = []
        self._snapshots = deque(maxlen=POLL_INTERVAL * 2)
        self._set_url_default()
        self._refresh_id = self.set_interval(POLL_INTERVAL, self.refresh_metrics)

    def _set_url_default(self):
        model = _get_model_param().split("=")[-1]
        self._url.update(f"llama.cpp metrics → localhost:8080?model={model}")
        self._status.update("● Connecting...")
        self._status.add_class("status-disconnected")

    def get_metrics(self) -> MetricSnapshot | None:
        """Busca uma nova leitura das métricas."""
        return self._client.poll()

    watch_metrics = get_metrics

    def refresh_metrics(self):
        """Atualiza o dashboard com nova leitura."""
        if not hasattr(self, '_connect_attempts'):
            self._connect_attempts = 0
        self._connect_attempts += 1

        snap = self.get_metrics()
        if snap:
            dash = self.query_one("#dashboard", DashboardView)
            dash.update(snap)

            chart = self.query_one("#chart", HistoryChart)
            chart.add_point(snap.prompt_tps, snap.pct_cached, snap.gen_tps)

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
                    "● Disconnected — check compose.yaml for 'LLAMA_ARG_ENDPOINT_METRICS=true' env var"
                )


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
