"""SSD1306 OLED driver, ported from micropython-lib:
https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/display/ssd1306/ssd1306.py
(MIT licensed, copyright the MicroPython project contributors).

Changes from upstream -- see display/DEVELOPMENT.md for the full
investigation, this is the short version:
  - The framebuf.FrameBuffer drawing calls (fill/pixel/line/hline/vline/
    rect/fill_rect/text/scroll) are used completely unmodified. CanMV's
    cached stub (framebuf.pyi) exposes the same method set including
    MONO_VLSB, so upstream's reliance on framebuf.FrameBuffer needed no
    change.
  - SSD1306_I2C.write_cmd/write_framebuf are also unmodified: CanMV's
    machine.I2C.writeto(addr, buf) and .writevto(addr, vector) have the
    same signatures upstream relies on (confirmed against the cached
    machine.pyi stub).
  - Net result: this file is, as far as could be checked without the real
    board, a straight port with no SSD1306-specific logic changed. The
    only CanMV-specific code (FPIOA pin setup, I2C object construction) is
    deliberately kept OUT of this file and lives in src/oled_device.py
    instead, so this driver stays close to upstream.

UNVERIFIED (no real SSD1306/VLT-OL016 silicon tested this session):
  - That machine.I2C.writevto() actually performs a single START..STOP
    multi-buffer write the way upstream's write_framebuf() assumes, rather
    than something else. The stub signature matches the standard
    MicroPython API name and shape, but its real behavior on this
    firmware was not exercised.
  - That VLT-OL016 is in fact SSD1306-compatible and uses a standard
    128x64 init sequence (see display/README.md).
"""

import framebuf

# SSD1306 commands (as named in the upstream driver / Solomon Systech datasheet).
SET_CONTRAST = 0x81
SET_ENTIRE_ON = 0xA4
SET_NORM_INV = 0xA6
SET_DISP = 0xAE
SET_MEM_ADDR = 0x20
SET_COL_ADDR = 0x21
SET_PAGE_ADDR = 0x22
SET_DISP_START_LINE = 0x40
SET_SEG_REMAP = 0xA0
SET_MUX_RATIO = 0xA8
SET_COM_OUT_DIR = 0xC0
SET_DISP_OFFSET = 0xD3
SET_COM_PIN_CFG = 0xDA
SET_DISP_CLK_DIV = 0xD5
SET_PRECHARGE = 0xD9
SET_VCOM_DESEL = 0xDB
SET_CHARGE_PUMP = 0x8D


class SSD1306(framebuf.FrameBuffer):
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def init_display(self):
        for cmd in (
            SET_DISP | 0x00,  # display off
            SET_MEM_ADDR, 0x00,  # horizontal addressing mode
            SET_DISP_START_LINE | 0x00,
            SET_SEG_REMAP | 0x01,  # column addr 127 mapped to SEG0
            SET_MUX_RATIO, self.height - 1,
            SET_COM_OUT_DIR | 0x08,  # scan from COM[N-1] to COM0
            SET_DISP_OFFSET, 0x00,
            SET_COM_PIN_CFG, 0x02 if self.height == 32 else 0x12,
            SET_DISP_CLK_DIV, 0x80,
            SET_PRECHARGE, 0x22 if self.external_vcc else 0xF1,
            SET_VCOM_DESEL, 0x30,  # 0.83*Vcc
            SET_CONTRAST, 0xFF,
            SET_ENTIRE_ON,  # output follows RAM contents
            SET_NORM_INV,  # not inverted
            SET_CHARGE_PUMP, 0x10 if self.external_vcc else 0x14,
            SET_DISP | 0x01,
        ):  # display on
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    def show(self):
        x0 = 0
        x1 = self.width - 1
        if self.width == 64:
            # displays with width of 64 pixels are shifted by 32
            x0 += 32
            x1 += 32
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(x0)
        self.write_cmd(x1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_framebuf()


class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        # Data/command byte + buffer-to-send, used in write_list below so
        # the whole framebuffer goes out as one writevto() transaction
        # (matches upstream exactly -- see module docstring).
        self.write_list = [b"\x40", None]
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80  # Co=1, D/C#=0
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_framebuf(self):
        self.write_list[1] = self.buffer
        self.i2c.writevto(self.addr, self.write_list)
