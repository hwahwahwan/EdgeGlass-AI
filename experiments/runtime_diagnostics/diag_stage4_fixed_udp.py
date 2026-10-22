"""Runtime diagnostics stage 4: camera + AI + web + UDP mouse transport, but
with MOUSE_UDP_AUTO_DISCOVER forced off (fixed destination IP, no subnet
scan at all). This isolates "does any UDP activity during the AI/web loop
cause instability" from "does the 253-target discovery burst specifically
cause instability" (see docs/WORK_TRACKER.md 2026-10-23 entry).

Deploy target: /sdcard/runtime_diagnostics/ (separate from /sdcard/smart_glass/,
same convention as experiments/wifi_test/ -- never mixed with the production
path). Imports the already-verified firmware/ modules by inserting
/sdcard/smart_glass onto sys.path; does not modify any firmware/ file.

Bounded by the operator stopping it (canmv_stop_script) after a short
observation window -- intentionally not a fixed frame count, so it can be
stopped immediately the moment anything looks wrong.
"""

import sys

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import config

# --- Diagnostic-only overrides (never touches the files on disk) ---
config.MOUSE_UDP_AUTO_DISCOVER = False
config.MOUSE_UDP_HOST = "192.168.45.62"  # Mac's real IP for this test session
config.MOUSE_UDP_PORT = 9000
config.VERBOSE_ORCHESTRATOR_LOGS = True  # reuse existing STEP:/mem_free/fps logs

import smart_glass_server

if __name__ == "__main__":
    print("[DIAG4] fixed-IP UDP (no discovery scan), auto_discover=%r host=%r" % (
        config.MOUSE_UDP_AUTO_DISCOVER, config.MOUSE_UDP_HOST))
    smart_glass_server.main(transport_kind="udp", enable_web=True)
