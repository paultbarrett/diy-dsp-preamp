# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import time
import threading
import redis

# display
import board
import busio
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

import pymedia_logger
from pymedia_cdsp import redis_cdsp_ping

# ---------------------

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
DISPLAY_I2C_SCL = board.SCL
DISPLAY_I2C_SDA = board.SDA
DISPLAY_I2C_ADDRESS = 0x3C
DISPLAY_BG_COLOR = 0
DISPLAY_FG_COLOR = 255
DISPLAY_CONTRAST = 0
DISPLAY_FONT_SMALL = 'DejaVuSansMono.ttf'
DISPLAY_FONT_MEDIUM = DISPLAY_FONT_SMALL
DISPLAY_FONT_LARGE = DISPLAY_FONT_SMALL
DISPLAY_FONT_SYMBOLS = DISPLAY_FONT_SMALL
# font size != font height; use print_font_sizes.py to find sizes
DISPLAY_FONT_SMALL_SIZE = 14
DISPLAY_FONT_MEDIUM_SIZE = 32
DISPLAY_FONT_LARGE_SIZE = 62
DISPLAY_FONT_SYMBOLS_SIZE = 20
DISPLAY_X_OFFSET = 8
DISPLAY_LINE_SPACING = 2
DISPLAY_VOLUME_UNIT = "dB"
DISPLAY_MAX_PLAYER_STATS_AGE = 10   # seconds
DISPLAY_UPDATE_INTERVAL = 10    # seconds
DISPLAY_TIMEOUT_AUTO_OFF = 0    # 0 to disable (seconds)

# ---------------------

class Display():

    def __init__(self, _redis, pubsubs):
        self._log = pymedia_logger.get_logger(__class__.__name__)
        self._redis = _redis
        self._i2c = busio.I2C(board.SCL, board.SDA)
        # 128x16 Yellow | 128x48 Sky Blue
        self._disp = adafruit_ssd1306.SSD1306_I2C(
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT,
                busio.I2C(DISPLAY_I2C_SCL, DISPLAY_I2C_SDA),
                addr=DISPLAY_I2C_ADDRESS,
                )
        self._disp.contrast(DISPLAY_CONTRAST)
        self._timeout_auto_off = DISPLAY_TIMEOUT_AUTO_OFF
        self._update_id = 0
        self._is_blank = False
        self._pubsubs = pubsubs

        self.t_wait_events = threading.Thread(target = self.wait_events)
        self.t_wait_events.daemon = True

        try:
            # Load default font.
            #self._font_small = ImageFont.load_default()
            self._font_small = ImageFont.truetype(DISPLAY_FONT_SMALL,
                    DISPLAY_FONT_SMALL_SIZE)
            self._font_medium = ImageFont.truetype(DISPLAY_FONT_MEDIUM,
                    DISPLAY_FONT_MEDIUM_SIZE)
            self._font_large = ImageFont.truetype(DISPLAY_FONT_LARGE,
                    DISPLAY_FONT_LARGE_SIZE)
            self._font_symbols = ImageFont.truetype(DISPLAY_FONT_SYMBOLS,
                    DISPLAY_FONT_SYMBOLS_SIZE)
        except FileNotFoundError as ex:
            self._log.error("missing font file in path (default: font5x8.bin)")
            raise SystemExit from ex

        ( self._volume_unit_width, self._volume_unit_height ) = \
                self._font_small.getsize(DISPLAY_VOLUME_UNIT)

        self.blank()    # clear display

    def blank(self):
        """Blank display (= fill with black)."""
        if not self._is_blank:
            self._disp.fill(0)
            self._disp.show()
            self._is_blank = True

    def draw_functions(self, draw):
        """Default drawing functions: draw banner and CamillaDSP volume."""
        self.draw_status_bar(draw)
        self.draw_cdsp_volume(draw)

    # https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html
    def draw_status_bar(self, draw):
        """Draw the banner (upper display part).

        Banner: player status | config index | signal RMS | signal peak
        """
        player_is_stale = not self._redis.check_timestamp(
                "PLAYER:last_alive",
                DISPLAY_MAX_PLAYER_STATS_AGE,
                )
        max_playback_signal_rms = (
            self._redis.get_s("CDSP:max_playback_signal_rms"))
        max_playback_signal_peak = (
            self._redis.get_s("CDSP:max_playback_signal_peak"))
        config_index = self._redis.get_s("CDSP:config_index")

        # draw player status symbols
        # \u25CC: off: '◌'
        # \u25B7: play '▷'
        # \u25A1: stop '□'
        player_status = " " if player_is_stale else (
                '\u25CC' if not self._redis.get_s("PLAYER:power") else (
                    '\u25B7' if self._redis.get_s("PLAYER:isplaying") else (
                    '\u25A1')))

        # https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html
        draw.text(
            (DISPLAY_X_OFFSET, 16 - DISPLAY_LINE_SPACING), player_status,
            font=self._font_symbols, fill=DISPLAY_FG_COLOR, spacing=0,
            anchor='lb')

        # draw config index (0->'A', 1->'B, ...) and rms/peak levels
        text = "{}{} {:02d}/{:02d}".format(
                chr(65 + config_index) if config_index is not None else ' ',
                '-' if self._redis.get_s("CDSP:switching_config") else ' ',
                max_playback_signal_rms if (
                    max_playback_signal_rms is not None
                    and max_playback_signal_rms > -99
                    )
                    else -99,
                max_playback_signal_peak if (
                    max_playback_signal_peak is not None
                    and max_playback_signal_peak > -99
                    )
                    else -99
                )
        self._log.debug("banner text is '%s'", text)
        draw.text(
            (self._disp.width - DISPLAY_X_OFFSET, 16 - DISPLAY_LINE_SPACING),
            text, font=self._font_small, fill=DISPLAY_FG_COLOR, spacing=0,
            anchor='rb')

    def draw_cdsp_volume(self, draw):
        """Draw the cdsp volume and mute status (main display area)."""

        vol = self._redis.get_s("CDSP:volume")
        if not vol:
            return
        vol = f'{int(vol)}'

        # draw unit
        draw.text(
            (self._disp.width - DISPLAY_X_OFFSET, self._disp.height),
            DISPLAY_VOLUME_UNIT, font=self._font_small,
            fill=DISPLAY_FG_COLOR, spacing=0, anchor='rb')

        # draw text
        draw.text(
            (self._disp.width - self._volume_unit_width - DISPLAY_X_OFFSET,
             self._disp.height),
            vol,
            font=self._font_large, fill=DISPLAY_FG_COLOR,
            spacing=0, anchor='rb')

        # draw mute
        if self._redis.get_s("CDSP:mute"):
            draw.text(
                (self._disp.width - DISPLAY_X_OFFSET, self._disp.height -
                 self._volume_unit_height - DISPLAY_LINE_SPACING), "M",
                font=self._font_symbols, fill=DISPLAY_FG_COLOR, spacing=0,
                anchor='rb')

    def update_condition(self):
        """Default update condition: refresh when CamillaDSP is active."""
        self._log.debug("Default condition: check Redis/CamillaDSP status")
        if not redis_cdsp_ping(self._redis, max_age=10):
            return False
        return True

    def update(self):
        """Update (refresh) the display.

        Blocking function, so executed from within a thread - see wait_events().
        Detect (return) when a new thread has "taken over" to avoid screen
        glitches and needless resources consumption.
        """

        # save the current thread id for later comparison
        update_id = self._update_id

        self._log.debug("refreshing display - thread ID is %d", update_id)

        if not self.update_condition():
            self._log.debug("Condition was False - display is off")
            self.blank()
            return

        start_render = time.monotonic()

        # Create a blank image for drawing.
        # Make sure to create image with mode '1' for 1-bit color.
        image = Image.new("1", (self._disp.width, self._disp.height))
        # Get a drawing object to draw the image on
        draw = ImageDraw.Draw(image)

        # Draw a black filled box to clear the image.
        draw.rectangle((0, 0, self._disp.width, self._disp.height),
                         outline=0, fill=DISPLAY_BG_COLOR)

        # stop if another thread took over
        if self._update_id != update_id:
            self._log.debug("Won't redraw - new event available (s:%d|c:%d)",
                           self._update_id, update_id)
            return

        # draw
        self.draw_functions(draw)

        # stop if another thread took over
        if self._update_id != update_id:
            self._log.debug("Won't redraw - new event available (s:%d|c:%d)",
                           self._update_id, update_id)
            return

        # finally update display
        self._is_blank = False
        self._disp.image(image)
        self._disp.show()

        self._log.debug("render: %s", time.monotonic() - start_render)

    def wait_events(self):
        """Wait for redis events / update display on each event."""

        # bug: 'ignore_subscribe_messages' doesn't seem to work with
        # get_message(timeout=...) so we'll immediately get as many messages as
        # subscription channels at startup
        self._log.debug("waiting events on pubsubs %s", self._pubsubs)
        pubsub = self._redis.redis.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(self._pubsubs)
        except redis.exceptions.RedisError as ex:
            self._log.error(ex)
            return

        while True:
            try:
                message = pubsub.get_message(timeout=DISPLAY_UPDATE_INTERVAL)
                if message:
                    self._log.debug("received message %s", message)
                else:
                    self._log.debug("timeout (%s seconds)",
                                   DISPLAY_UPDATE_INTERVAL)
                thread = threading.Thread(target = self.update)
                self._update_id += 1
                thread.start()
            except redis.exceptions.RedisError as ex:
                self._log.error(ex)
                return
