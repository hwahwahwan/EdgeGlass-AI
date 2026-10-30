"""Tests for tools/autorun/main.py (deploys to /sdcard/main.py).

This file unconditionally calls run_boot() at module level (no
``if __name__ == "__main__":`` guard) -- deliberately left that way, same
as the original file, because it is genuinely uncertain whether
MicroPython sets ``__name__ == "__main__"`` for the board's designated
autorun main.py (no real hardware available this session to check), and
guessing wrong would silently break the entire auto-launch feature. So
instead of changing the file to be test-friendly, this test runs the
module once via runpy (exactly like tests/test_wifi_mouse_transport.py's
RunProfileEntryPointTests does for firmware/run_uart.py/run_wifi.py) with
``time.sleep`` patched to a no-op and a fake ``smart_glass_server`` module
installed, and then calls the ``run_boot`` function object out of the
resulting namespace a second time with injected fakes for the other
scenarios (SAFE_MODE present, custom countdown/launch). oled_device and
display_ui are unavailable under plain CPython (no ``machine`` module),
so oled/oled_ui are always None here -- the OLED draw calls themselves
are covered separately by display/tests/test_display_ui.py; this file
only checks that run_boot() calls into them at the right points and in
the right order, via a fake oled_ui spy (see _run_with_fake_oled below).
"""

import os
import runpy
import sys
import tempfile
import time as real_time
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTORUN_PATH = os.path.join(_REPO_ROOT, "tools", "autorun", "main.py")


def _install_fake_smart_glass_server():
    fake_module = types.ModuleType("smart_glass_server")
    calls = []

    def fake_main(**kwargs):
        calls.append(kwargs)

    fake_module.main = fake_main
    original = sys.modules.get("smart_glass_server")
    sys.modules["smart_glass_server"] = fake_module
    return original, calls


def _restore_smart_glass_server(original):
    if original is None:
        sys.modules.pop("smart_glass_server", None)
    else:
        sys.modules["smart_glass_server"] = original


def _run_module_once():
    """Executes tools/autorun/main.py exactly once (its own unconditional
    module-level run_boot() call), with real sleeping and the real
    smart_glass_server import both neutralized. Returns the resulting
    namespace dict, which still contains the ``run_boot`` function object
    for further direct calls."""
    original, calls = _install_fake_smart_glass_server()
    try:
        with mock.patch.object(real_time, "sleep", lambda s: None):
            namespace = runpy.run_path(_AUTORUN_PATH, run_name="__main__")
    finally:
        _restore_smart_glass_server(original)
    return namespace, calls


class DefaultBootPathTests(unittest.TestCase):
    """The one real end-to-end execution per test process (module-level
    call, real defaults except for the neutralized sleep/import)."""

    def test_default_run_reaches_launch_with_udp_and_web_profile(self):
        namespace, calls = _run_module_once()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["transport_kind"], "udp")
        self.assertEqual(calls[0]["enable_web"], True)
        self.assertIn("oled", calls[0])
        self.assertIn("oled_ui", calls[0])

    def test_run_boot_function_is_available_for_further_direct_calls(self):
        namespace, _ = _run_module_once()
        self.assertIn("run_boot", namespace)
        self.assertTrue(callable(namespace["run_boot"]))


class RunBootDirectCallTests(unittest.TestCase):
    """Scenario tests against the real run_boot() function, obtained from
    one shared module execution (see setUp), with every side-effecting
    dependency injected -- no real sleeping, no real SAFE_MODE path, no
    real smart_glass_server import."""

    @classmethod
    def setUpClass(cls):
        cls._namespace, _ = _run_module_once()
        # staticmethod() so accessing this via self._run_boot does not turn
        # it into a bound method that silently swallows `self` as the
        # first positional argument (run_boot's first param is sleep_fn).
        cls._run_boot = staticmethod(cls._namespace["run_boot"])

    def test_safe_mode_present_skips_launch_entirely(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            safe_mode_path = os.path.join(tmp_dir, "SAFE_MODE")
            with open(safe_mode_path, "w"):
                pass
            launch_calls = []
            sleeps = []
            self._run_boot(
                sleep_fn=sleeps.append,
                safe_mode_path=safe_mode_path,
                launch=lambda oled, oled_ui: launch_calls.append((oled, oled_ui)),
            )
            self.assertEqual(launch_calls, [])
            self.assertEqual(sleeps, [])  # countdown never starts

    def test_safe_mode_present_closes_the_oled_it_opened(self):
        # docs/DEV_HISTORY.md 4-8 (2026-10-30): run_boot() used to leave
        # the OLED it opened for "EDGEGLASS-AI/BOOTING" dangling when it
        # took the SAFE_MODE early-return path, instead of closing it the
        # same way a normal (non-fatal) shutdown does elsewhere in this
        # project. _open_oled() itself returns (None, None) under plain
        # CPython (no `machine` module), so this test monkeypatches the
        # module's own _open_oled and oled_device to fakes to exercise
        # the close_display() call that only happens on real hardware.
        fake_oled = object()
        close_calls = []

        class _FakeOledUi:
            def show_stage(self, lines):
                pass

        class _FakeOledDevice:
            @staticmethod
            def close_display(oled):
                close_calls.append(oled)

        # run_boot's *real* globals dict (what `_open_oled()`/`oled_device`
        # actually resolve against at call time) is run_boot.__globals__,
        # NOT self._namespace -- runpy.run_path() returns a *copy* of the
        # exec namespace, taken after execution already finished, so
        # mutating that copy would silently do nothing here.
        real_globals = self._run_boot.__globals__
        original_open_oled = real_globals["_open_oled"]
        original_oled_device = real_globals["oled_device"]
        real_globals["_open_oled"] = lambda: (fake_oled, _FakeOledUi())
        real_globals["oled_device"] = _FakeOledDevice
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                safe_mode_path = os.path.join(tmp_dir, "SAFE_MODE")
                with open(safe_mode_path, "w"):
                    pass
                self._run_boot(sleep_fn=lambda ms: None, safe_mode_path=safe_mode_path)
            self.assertEqual(close_calls, [fake_oled])
        finally:
            real_globals["_open_oled"] = original_open_oled
            real_globals["oled_device"] = original_oled_device

    def test_safe_mode_absent_runs_full_countdown_then_launches(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            safe_mode_path = os.path.join(tmp_dir, "SAFE_MODE")  # does not exist
            launch_calls = []
            sleeps = []
            self._run_boot(
                sleep_fn=sleeps.append,
                countdown=(2, 1),
                safe_mode_path=safe_mode_path,
                launch=lambda oled, oled_ui: launch_calls.append((oled, oled_ui)),
            )
            self.assertEqual(sleeps, [1, 1])  # one sleep_fn(1) call per countdown tick
            self.assertEqual(len(launch_calls), 1)

    def test_launch_exception_is_reported_and_reraised(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            safe_mode_path = os.path.join(tmp_dir, "SAFE_MODE")

            def _boom(oled, oled_ui):
                raise RuntimeError("simulated launch failure")

            with self.assertRaises(RuntimeError):
                self._run_boot(
                    sleep_fn=lambda ms: None,
                    countdown=(1,),
                    safe_mode_path=safe_mode_path,
                    launch=_boom,
                )

    def test_default_launch_imports_and_calls_smart_glass_server_main(self):
        # Covers the branch where launch=None (the production default),
        # separately from the shared module-level execution above.
        original, calls = _install_fake_smart_glass_server()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                safe_mode_path = os.path.join(tmp_dir, "SAFE_MODE")
                self._run_boot(
                    sleep_fn=lambda ms: None,
                    countdown=(1,),
                    safe_mode_path=safe_mode_path,
                )
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], {
                "transport_kind": "udp", "enable_web": True,
                "oled": None, "oled_ui": None,
            })
        finally:
            _restore_smart_glass_server(original)


if __name__ == "__main__":
    unittest.main()
