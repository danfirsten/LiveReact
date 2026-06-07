"""Application supervisor: wires the components, owns the lifecycle.

Phase 0 wiring is intentionally thin — a frame buffer, an output backend, and the
DMX writer thread, paced by a real clock and shut down cleanly on Ctrl-C or a stop
signal. Later phases attach the metronome, input sources, show engine, and UI to
the same supervisor without changing its shutdown contract.
"""

from __future__ import annotations

import logging
import signal
import threading
from dataclasses import dataclass

from .clock import Clock, RealClock
from .core.frame_buffer import DmxFrameBuffer
from .output.base import OutputBackend
from .output.null_log import NullLogBackend
from .output.writer import DmxWriter

log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    demo: bool = True
    dmx_rate_hz: float = 40.0
    duration: float | None = None  # bounded run for testing; None = run until signal


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

        # --- core pipeline (Phase 0) ---
        self.frame_buffer = DmxFrameBuffer()
        self.backend = backend or NullLogBackend(log_every=int(self.config.dmx_rate_hz))
        self.writer = DmxWriter(
            self.frame_buffer,
            self.backend,
            self.clock,
            self.stop_event,
            hz=self.config.dmx_rate_hz,
        )

        # All hardware-touching, non-daemon threads to join on shutdown.
        self._threads: list[threading.Thread] = [self.writer]

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
        log.info("Shutdown complete (%d frames sent)", self.writer.frames_sent)

    def serve(self) -> None:
        """Start threads and block until a stop signal, Ctrl-C, or duration end."""
        self._install_signal_handlers()
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

    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("Received signal %s", signum)
            self.stop_event.set()

        # signal.signal only works on the main thread; ignore if not (e.g. tests).
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError, AttributeError):
                pass
