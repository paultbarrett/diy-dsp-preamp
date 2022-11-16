#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

# a standalone CamillaDSP "remote volume" (no redis, no display, etc.)

import logging
import time
import gpiod

from camilladsp import CamillaConnection, CamillaError, ProcessingState

import pymedia
import rotary

# ---------------------

ROTARY_ENCODER_DISCARD_TIME_WINDOW = 0.1
ROTARY_ENCODER_MAX_AGE = 0.15

CDSP_SERVER = "localhost"
CDSP_PORT = 1234
CDSP_VOLUME_MIN = -60
CDSP_VOLUME_MAX = -12
CDSP_VOLUME_STEP = 1

# ----------------

class SetVolume():
    def __init__(self, _cdsp):
        self._log = logging.getLogger(self.__class__.__name__)
        self._cur_event_id = 0
        self._cdsp = _cdsp
        self._last_vol_event_time = 0
        self._last_vol_event_value = None
        self._vol_callback = self.cdsp_set_volume

    def cdsp_set_volume(self, value, direction):
        """Send (publish) volume up/down actions for CamillaDSP."""
        if self._last_vol_event_value:
            vol_incr = value - self._last_vol_event_value
        else:
            vol_incr = 1 if direction == rotary.DIR_CW else -1

        self._cdsp.incr_volume(vol_incr)

    def volume_event(self, value, direction):
        """Process a volume event.

        We're trying to provide adequate visual cue of volume change without
        flooding cdsp with volume change requests:
        - run event if the previous event is older than ROTARY_ENCODER_MAX_AGE
        - otherwise, wait for ROTARY_ENCODER_DISCARD_TIME_WINDOW seconds then
          process event if no new event has arrived meanwhile
        -> this means we may discard events, but we send the relative volume
        (value), not just +1/-1 increments so we don't loose data.

        Note: blocking (time.sleep()) so should be executed as a thread
        """
        self._cur_event_id += 1
        event_id = self._cur_event_id
        set_vol = False
        if time.time() - self._last_vol_event_time > ROTARY_ENCODER_MAX_AGE:
            self._log.debug("thread id # %s: last event time was more than"
                          " %fs ago - running",
                          event_id, ROTARY_ENCODER_MAX_AGE)
            set_vol = True
        else:
            self._log.debug("thread id # %s: an event happened less than %fs"
                          " ago - waiting %fs to proceed", event_id,
                          ROTARY_ENCODER_MAX_AGE,
                          ROTARY_ENCODER_DISCARD_TIME_WINDOW)
            time.sleep(ROTARY_ENCODER_DISCARD_TIME_WINDOW)
            if event_id == self._cur_event_id:
                self._log.debug("thread id # %s: no new event - running",
                              event_id)
                set_vol = True
            else:
                self._log.debug("thread id # %s: event id %s took over",
                              event_id, self._cur_event_id)

        if set_vol:
            self._vol_callback(value, direction)
            self._last_vol_event_value = value
            self._last_vol_event_time = time.time()


class CDsp():
    def __init__(self, server, port):
        self._log = logging.getLogger(self.__class__.__name__)
        self._conn = pymedia.ConnParam(server, port)
        self._setting_volume = False
        self._cdsp = None
        self.threads = pymedia.SimpleThreads()
        self.threads.add_target(self.connect_loop)

    def connect_loop(self):
        """Connect to CamillaDSP (loop).

        Keep trying to connect to CamillaDSP, and upon connection update stats,
        wake-up sub, etc.

        Blocking, executed from within a thread (self.t_connect_loop)
        """
        self._cdsp = CamillaConnection(self._conn.server, self._conn.port)
        connect_attempts = 0
        while True:
            if not self._cdsp.is_connected():
                try:
                    self._cdsp.connect()
                except (ConnectionRefusedError, CamillaError, IOError) as ex:
                    # log (debug) every time, but log (info) once
                    self._log.debug("Couldn't connect to CamillaDSP: %s", ex)
                    if connect_attempts == 0:
                        self._log.info("Couldn't connect to CamillaDSP")
                    connect_attempts += 1
                else:
                    connect_attempts = 0
                    self._log.info("Connected to CamillaDSP on %s:%d"
                                  " - version:%s", self._conn.server,
                                  self._conn.port,
                                  self._cdsp.get_version()
                                  )
            time.sleep(2)


    def is_on(self):
        """Check if CamillaDSP is active.

        Active: we're connected and CamillaDSP is running or paused
        """
        try:
            if (self._cdsp and self._cdsp.is_connected()
                and self._cdsp_wp("get_state") in [ ProcessingState.RUNNING,
                                             ProcessingState.PAUSED ]):
                return True
        except (ConnectionRefusedError, CamillaError, IOError) as ex:
            self._log.warning("Exception: %s", ex)

        return False

    def mute(self, mode="toggle"):
        """Mute/unmute/toggle mute."""

        set_mute = True
        if mode == "toggle":
            if self._cdsp_wp("get_mute"):
                set_mute = False
        elif mode == "mute":
            pass
        elif mode == "unmute":
            set_mute = True
        else:
            self._log.warning("mode '%s' isn't defined", mode)
            return

        if set_mute:
            self._cdsp_wp("set_mute", True)
        else:
            self._cdsp_wp("set_mute", False)

    def incr_volume(self, vol_incr):
        self.set_volume(self._cdsp_wp("get_volume") + vol_incr)

    def set_volume(self, vol):
        """Set volume."""
        if not CDSP_VOLUME_MIN <= vol <= CDSP_VOLUME_MAX:
            self._log.debug("volume '%s' is out of range", vol)
            vol = CDSP_VOLUME_MAX if vol > CDSP_VOLUME_MAX else CDSP_VOLUME_MIN

        self._log.debug("Setting volume to '%s'", vol)
        # avoid setting volume concurrently (possible as this task is run as
        # a thread)
        while self._setting_volume:
            self._log.debug("A volume change task is already set - wait")
            time.sleep(0.5)
        self._setting_volume = True
        self._cdsp_wp("set_volume", vol)
        self._setting_volume = False


    def _cdsp_wp(self, func_name, *args, **kwargs):
        """Wrapper function to CamillaDSP functions.

        See https://github.com/HEnquist/pycamilladsp#reading-status
        """
        res = None
        func = getattr(self._cdsp, str(func_name))
        try:
            res = func(*args, **kwargs)
        except ConnectionRefusedError as ex:
            self._log.error(("Can't connect to CamillaDSP, is it running?"
                " Error: %s") , ex)
        except CamillaError as ex:
            self._log.error("CamillaDSP replied with error: %s", ex)
        except IOError as ex:
            self._log.error("Websocket is not connected: %s", ex)
        return res



# ----------------

if __name__ == '__main__':

    cdsp = CDsp(CDSP_SERVER, CDSP_PORT)

    v = SetVolume(cdsp)

    gpiochip0 = gpiod.Chip("gpiochip0")
    r = rotary.RotaryEncoder(gpiochip0, 16, 15, callback=v.volume_event,
                             threaded_callback=True)

    # add rotary encoder wait_events() loop to the list of threads
    cdsp.threads.add_target(r.wait_events)

    cdsp.threads.start()

    try:
        cdsp.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
