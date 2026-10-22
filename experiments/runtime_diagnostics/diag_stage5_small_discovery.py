"""Runtime diagnostics stage 5: camera + AI + web + UDP mouse transport with
REAL @HELLO/@ACK discovery, but the candidate list is monkey-patched down to
a handful of addresses (including the Mac's real IP) instead of the real
/24 subnet scan (253 targets). Isolates "does the discovery mechanism itself
work" from "does a 253-address burst cause instability" -- see
docs/WORK_TRACKER.md 2026-10-23 entry. Deliberately does NOT re-run the
253-target case.

Deploy target: /sdcard/runtime_diagnostics/ (separate from /sdcard/smart_glass/).
Does not modify any firmware/ file -- discovery.compute_scan_targets is
monkey-patched only inside this throwaway process.

Bounded by the operator stopping it (canmv_stop_script) after a short
observation window.
"""

import sys

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import config
import discovery

# --- Diagnostic-only overrides (never touches the files on disk) ---
config.MOUSE_UDP_AUTO_DISCOVER = True
config.MOUSE_UDP_PORT = 9000
config.VERBOSE_ORCHESTRATOR_LOGS = True

_SMALL_TARGETS = ["192.168.45.62", "192.168.45.1", "192.168.45.99", "192.168.45.123", "192.168.45.200"]


def _tiny_compute_scan_targets(ip, netmask, max_hosts=64):
    print("[DIAG5] using %d-address diagnostic target list instead of a real /24 scan" % len(_SMALL_TARGETS))
    return list(_SMALL_TARGETS)


discovery.compute_scan_targets = _tiny_compute_scan_targets

import smart_glass_server

if __name__ == "__main__":
    print("[DIAG5] small-scale discovery (%d targets), real Mac IP included" % len(_SMALL_TARGETS))
    smart_glass_server.main(transport_kind="udp", enable_web=True)
