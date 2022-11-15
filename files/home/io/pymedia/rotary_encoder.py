#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import time
import gpiod

import pymedia
import rotary

# ---------------------

ROTARY_ENCODER_DISCARD_TIME_WINDOW = 0.1
ROTARY_ENCODER_MAX_AGE = 0.15

# ----------------

class SetVolume():
    def __init__(self, _redis):
        self._log = logging.getLogger(self.__class__.__name__)
        self._redis = _redis
        self._cur_event_id = 0
        self._last_vol_event_time = 0
        self._last_vol_event_value = None
        self._vol_callback = self.cdsp_set_volume

    def cdsp_set_volume(self, value, direction):
        """Send (publish) volume up/down actions for CamillaDSP."""
        if self._last_vol_event_value:
            vol_incr = value - self._last_vol_event_value
        else:
            vol_incr = 1 if direction == rotary.DIR_CW else -1

        self._redis.send_action('CDSP', f"set_volume:{vol_incr}")

    def volume_event(self, value, direction):
        """Process a volume event.

        We're trying to provide adequate visual cue of volume change without
        flooding cdsp and the display with volume change requests:
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


# ----------------

if __name__ == '__main__':

    gpiochip0 = gpiod.Chip("gpiochip0")

    v = SetVolume(pymedia.RedisHelper('ROTARY_ENCODER'))

    r = rotary.RotaryEncoder(gpiochip0, 16, 15, callback=v.volume_event,
                             threaded_callback=True)

    r.wait_events()
