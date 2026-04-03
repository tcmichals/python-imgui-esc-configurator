"""ImGui ESC configurator application entry point."""

from __future__ import annotations

import os
import sys
import time

from imgui_bundle import immapp

if __package__ in {None, ""}:
    PYTHON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if PYTHON_ROOT not in sys.path:
        sys.path.insert(0, PYTHON_ROOT)
    from imgui_bundle_esc_config import APP_VERSION
    from imgui_bundle_esc_config.app_state import create_app_state
    from imgui_bundle_esc_config.persistence import load_prefs, save_prefs
    from imgui_bundle_esc_config.runtime_logging import configure_runtime_logging, get_logger
    from imgui_bundle_esc_config.ui_main import drain_worker_events, render_main_window
    from imgui_bundle_esc_config.worker import CommandRefreshFirmwareCatalog, CommandRefreshPorts, EventFirmwareCatalogLoaded, WorkerController
else:
    from . import APP_VERSION
    from .app_state import create_app_state
    from .persistence import load_prefs, save_prefs
    from .runtime_logging import configure_runtime_logging, get_logger
    from .ui_main import drain_worker_events, render_main_window
    from .worker import CommandRefreshFirmwareCatalog, CommandRefreshPorts, EventFirmwareCatalogLoaded, WorkerController


def main() -> None:
    log_path = configure_runtime_logging()
    get_logger("app").info("Application startup; version=%s log file=%s", APP_VERSION, log_path)

    state = create_app_state()
    load_prefs(state)
    worker = WorkerController(msp_probe_on_connect=True, esc_stabilization_delay_s=1.2)

    # Eagerly populate catalog from disk cache so UI shows releases immediately.
    cached_snapshot = worker._firmware_catalog_client.load_catalog_snapshot()
    if cached_snapshot is not None:
        state.apply_event(EventFirmwareCatalogLoaded(snapshot=cached_snapshot, from_cache=True))

    worker.start()
    worker.enqueue(CommandRefreshPorts())
    worker.enqueue(CommandRefreshFirmwareCatalog())

    _last_save = time.monotonic()
    _SAVE_INTERVAL = 5.0  # seconds between auto-saves

    def gui() -> None:
        nonlocal _last_save
        drain_worker_events(state, worker)
        render_main_window(state, worker)
        now = time.monotonic()
        if now - _last_save >= _SAVE_INTERVAL:
            save_prefs(state)
            _last_save = now

    try:
        immapp.run(gui)
    finally:
        save_prefs(state)
        worker.stop()


if __name__ == "__main__":
    main()
