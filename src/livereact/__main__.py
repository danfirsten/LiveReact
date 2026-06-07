"""Command-line entry point: ``python -m livereact`` (or the ``livereact`` script).

Phase 0 supports demo mode only; ``--hardware`` is accepted but warns and falls
back to demo until the hardware backends land in Phase 7.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .app import App, AppConfig


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(threadName)-12s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="livereact",
        description="Beat-reactive DMX stage-lighting controller for live DJ sets.",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Run with synthetic data, no hardware (default).")
    mode.add_argument("--hardware", action="store_true", help="Use real devices (Enttec + Pro DJ Link + MIDI). UNTESTED.")
    p.add_argument("--rate", type=float, default=40.0, dest="rate", help="DMX refresh rate in Hz (default: 40).")
    p.add_argument("--duration", type=float, default=None, help="Run for N seconds then exit (default: until Ctrl-C).")
    p.add_argument("--visualize", action="store_true", help="Open the operator console + virtual rig (PySide6).")
    p.add_argument("--pdl-interface", default=None, help="Explicit network interface/IP for Pro DJ Link.")
    p.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR (default: INFO).")
    # Hardware bring-up tools (each runs and exits).
    p.add_argument("--fixture-test", action="store_true", help="Open the manual fixture-test panel (drive raw DMX).")
    p.add_argument("--midi-monitor", action="store_true", help="Print incoming MIDI to remap the XDJ, then exit.")
    p.add_argument("--net-check", action="store_true", help="Print Pro DJ Link network diagnostics and exit.")
    return p.parse_args(argv)


def _bringup_backend(demo: bool, rate: float):
    """Backend for the fixture-test tool: Enttec in hardware mode (fallback to
    NullLog), NullLog in demo."""
    from .output.null_log import NullLogBackend

    if not demo:
        try:
            from serial.tools import list_ports

            from .output.enttec import EnttecSerialBackend, select_enttec_port

            if select_enttec_port(list_ports.comports()):
                return EnttecSerialBackend()
            logging.getLogger("livereact").warning("No Enttec detected; using null backend.")
        except Exception:  # noqa: BLE001
            logging.getLogger("livereact").exception("Enttec unavailable; using null backend.")
    return NullLogBackend(log_every=int(rate))


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; ensure UTF-8 so diagnostics/logs never
    # crash on a non-ASCII character.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _configure_logging(args.log_level)
    log = logging.getLogger("livereact")

    demo = not args.hardware  # demo is the default; --demo is explicit-but-redundant

    # --- standalone bring-up tools (run and exit) ---
    if args.net_check:
        from .network import diagnostics
        print(diagnostics())
        return 0
    if args.midi_monitor:
        from .inputs.midi import monitor
        monitor(duration=args.duration)
        return 0
    if args.fixture_test:
        from .clock import RealClock
        from .fixtures.rig import load_rig
        from .ui.fixture_test import run_fixture_test
        rig = load_rig()
        backend = _bringup_backend(demo, args.rate)
        log.info("Fixture test using backend: %s", backend.name)
        run_fixture_test(rig, backend, RealClock(), dmx_rate_hz=args.rate)
        return 0

    config = AppConfig(demo=demo, dmx_rate_hz=args.rate, duration=args.duration,
                       pdl_interface=args.pdl_interface)
    app = App(config)

    if args.visualize:
        # Qt must own the main thread: run the pipeline in the background and the
        # operator console here; closing the window shuts everything down.
        from .ui.console import run_console

        app.install_signal_handlers()
        app.start()
        try:
            run_console(app)
        finally:
            app.shutdown()
    else:
        app.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
