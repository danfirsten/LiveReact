"""Application supervisor: wires the components, owns the lifecycle.

Phase 0 wiring is intentionally thin — a frame buffer, an output backend, and the
DMX writer thread, paced by a real clock and shut down cleanly on Ctrl-C or a stop
signal. Later phases attach the metronome, input sources, show engine, and UI to
the same supervisor without changing its shutdown contract.
"""

from __future__ import annotations

import logging
import queue
import signal
import threading
from dataclasses import dataclass

from . import config as app_config
from .clock import Clock, RealClock
from .core.frame_buffer import DmxFrameBuffer
from .core.metronome import Metronome
from .core.show_engine import ShowEngine
from .core.show_state import ShowState
from .engines.phrase import PhraseEngine
from .engines.reactive import ReactiveLayerEngine
from .fixtures.rig import Rig, load_rig
from .inputs.demo import DemoDataSource
from .merge.merge import ManualParams
from .output.base import OutputBackend
from .output.null_log import NullLogBackend
from .output.writer import DmxWriter

log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    demo: bool = True
    dmx_rate_hz: float = 40.0
    duration: float | None = None  # bounded run for testing; None = run until signal
    config_path: str | None = "config.json"  # None disables persistence


class App:
    """Owns the threads and the single stop event; guarantees clean shutdown."""

    def __init__(
        self,
        config: AppConfig | None = None,
        clock: Clock | None = None,
        backend: OutputBackend | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self.clock = clock or RealClock()
        self.stop_event = threading.Event()

        # --- output pipeline (Phase 0) ---
        self.frame_buffer = DmxFrameBuffer()
        self.backend = backend or NullLogBackend(log_every=int(self.config.dmx_rate_hz))
        self.writer = DmxWriter(
            self.frame_buffer,
            self.backend,
            self.clock,
            self.stop_event,
            hz=self.config.dmx_rate_hz,
        )

        # --- input pipeline (Phase 1): source -> queue -> metronome -> ShowState ---
        self.input_queue: "queue.Queue" = queue.Queue()
        self.show_state = ShowState()
        self.metronome = Metronome(self.input_queue, self.show_state, self.clock, self.stop_event)
        self.source = DemoDataSource(self.input_queue, self.clock, self.stop_event)

        # --- show pipeline (Phases 3-4): snapshot -> engines -> merge -> frame buffer ---
        self.rig: Rig = load_rig()
        self.manual = ManualParams()
        if self.config.config_path:
            app_config.load_into(self.manual, self.config.config_path)
        # In demo mode, simulate the operator arming lasers before the set so drop
        # scenes can show them. Lasers still boot off and only fire in drop scenes;
        # real/hardware mode leaves them disarmed until the operator arms (safety).
        if self.config.demo:
            self.manual.laser_enable = True
        self.phrase_engine = PhraseEngine()
        self.engines = [ReactiveLayerEngine(), self.phrase_engine]
        self.show_engine = ShowEngine(
            self.show_state, self.rig, self.frame_buffer, self.engines,
            self.manual, self.clock, self.stop_event,
        )

        # All non-daemon threads to join on shutdown. Order: producers first so the
        # metronome drains a quiescent queue last; the writer is independent.
        self._threads: list[threading.Thread] = [
            self.source, self.metronome, self.show_engine, self.writer,
        ]

    def start(self) -> None:
        log.info(
            "Starting LiveReact (mode=%s, dmx=%.0f Hz, backend=%s)",
            "demo" if self.config.demo else "hardware",
            self.config.dmx_rate_hz,
            self.backend.name,
        )
        for t in self._threads:
            t.start()

    def shutdown(self) -> None:
        if self.stop_event.is_set():
            return
        log.info("Shutting down...")
        self.stop_event.set()
        for t in self._threads:
            t.join(timeout=3.0)
            if t.is_alive():
                log.warning("Thread %s did not stop within timeout", t.name)
        if self.config.config_path:
            app_config.save_from(self.manual, self.config.config_path)
        log.info("Shutdown complete (%d frames sent)", self.writer.frames_sent)

    def serve(self) -> None:
        """Start threads and block until a stop signal, Ctrl-C, or duration end."""
        self.install_signal_handlers()
        self.start()
        try:
            if self.config.duration is not None:
                self.stop_event.wait(self.config.duration)
            else:
                # Wake periodically so the main thread stays responsive to signals.
                while not self.stop_event.wait(0.25):
                    pass
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt received")
        finally:
            self.shutdown()

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("Received signal %s", signum)
            self.stop_event.set()

        # signal.signal only works on the main thread; ignore if not (e.g. tests).
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError, AttributeError):
                pass
