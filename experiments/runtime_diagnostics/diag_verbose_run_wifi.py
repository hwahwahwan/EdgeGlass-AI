"""Runtime diagnostics: run the REAL production run_wifi.py entry point
(smart_glass_server.main(transport_kind="udp", enable_web=True)) with
VERBOSE_ORCHESTRATOR_LOGS temporarily turned on for this process only, so
main_loop FPS/mem and /stream frame/encode_ms lines are visible while a
real client pulls /stream -- used to sanity-check the
WEB_STREAM_MIN_INTERVAL_MS throttle fix (2026-10-23, see
docs/WORK_TRACKER.md) without touching firmware/config.py's committed
default (False).

Deploy target: /sdcard/runtime_diagnostics/.
"""

import sys

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import smart_glass_server as sgs

sgs.config.VERBOSE_ORCHESTRATOR_LOGS = True

if __name__ == "__main__":
    sgs.main(transport_kind="udp", enable_web=True)
