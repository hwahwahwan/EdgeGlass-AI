"""display/ configuration: pins, I2C, OLED geometry, update-rate limiting.

Named display_config.py (not config.py) because firmware/config.py is
deployed to the same flat board directory when display/ is wired into
smart_glass_server.py (see docs/DEV_HISTORY.md 4-3) -- two same-named
flat modules in one directory would shadow each other. Kept functionally
separate from firmware/config.py regardless -- display/ is an independent
module developed without the real VLT-OL016 panel in hand at first (see
README.md). Every value here that depends on real hardware is marked as
confirmed or candidate/unverified.
"""

# ============================================================
# I2C / FPIOA pin assignment -- CANDIDATE, NOT real-hardware verified.
# ============================================================
# No K230D-Zero board was available this session, so these could not be
# checked with FPIOA.help()/get_pin_num() the way the archived ST7789 LCD
# wiring was (see archive/st7789_lcd/README.md for that precedent). They
# are chosen to match the official CanMV K230 example
# examples/03-Machine/i2c_ssd1306.py exactly (hardware I2C2, GPIO11=SCL,
# GPIO12=SDA) rather than guessed or copied from an unrelated board.
#
# Confirmed by a project-wide read-only search (2026-10-23): firmware/
# does not claim GPIO11/12 anywhere. UART2 lives on fixed board pins 44/45
# (not FPIOA-assigned by our code at all), and the now-archived ST7789 LCD
# test used GPIO14/15/16/17/20/21 -- no overlap with 11/12.
I2C_ID = 2
PIN_SCL = 11
PIN_SDA = 12
I2C_FREQ = 400_000

# ============================================================
# OLED panel -- VLT-OL016, assumed SSD1306 (see README.md "확인된 사양").
# ============================================================
OLED_WIDTH = 128
OLED_HEIGHT = 64
# 0x3C is the far more common SSD1306 address; 0x3D is the other
# documented option. Unverified for this exact module -- oled_device.py
# logs i2c.scan() output so the real address can be read off the board.
OLED_I2C_ADDR = 0x3C

# ============================================================
# Hand landmark source coordinate space.
# ============================================================
# Matches firmware/smart_glass_server.py's AI_RGB888P_SIZE -- landmarks
# arrive in this pixel space from firmware/hand_tracker.py's HandTracker
# (see firmware/gesture_controller.py's use of the same `points` array).
# hand_renderer.py does not actually need these as hard limits (it only
# uses the landmarks' own bounding box), but they document the expected
# input space for anyone wiring display/ up to the real AI loop later.
AI_FRAME_WIDTH = 640
AI_FRAME_HEIGHT = 360

# ============================================================
# Layout
# ============================================================
STATUS_BAR_HEIGHT = 10   # bottom strip reserved for the MOVE/CLICK/... line
SKELETON_MARGIN_PX = 2   # keep the skeleton a couple pixels off every edge

# ============================================================
# Update throttling (see DEVELOPMENT.md "성능 고려").
# ============================================================
# display_ui.DisplayUI.update() can be called every AI frame; it only
# actually redraws (and does the I2C transfer) at most this often. Same
# reasoning as firmware/smart_glass_server.py's WEB_STREAM_MIN_INTERVAL_MS
# (docs/WORK_TRACKER.md section M/N) -- a slow peripheral's own refresh
# rate shouldn't dictate how often the caller is allowed to ask.
MIN_UPDATE_INTERVAL_MS = 100
