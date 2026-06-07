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
    mode.add_argument("--hardware", action="store_true", help="Use real devices (Phase 7+; falls back to demo for now).")
    p.add_argument("--rate", type=float, default=40.0, dest="rate", help="DMX refresh rate in Hz (default: 40).")
    p.add_argument("--duration", type=float, default=None, help="Run for N seconds then exit (default: until Ctrl-C).")
    p.add_argument("--visualize", action="store_true", help="Open the virtual rig visualizer (PySide6).")
    p.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR (default: INFO).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _configure_logging(args.log_level)
    log = logging.getLogger("livereact")

    demo = not args.hardware  # demo is the default; --demo is explicit-but-redundant
    if args.hardware:
        log.warning("Hardware mode not implemented yet (Phase 7); running in demo mode.")

    config = AppConfig(demo=demo, dmx_rate_hz=args.rate, duration=args.duration)
    app = App(config)

    if args.visualize:
        # Qt must own the main thread: run the pipeline in the background and the
        # visualizer here; closing the window shuts everything down.
        from .ui.visualizer import run as run_visualizer

        app.install_signal_handlers()
        app.start()
        try:
            run_visualizer(app.frame_buffer, app.rig)
        finally:
            app.shutdown()
    else:
        app.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
