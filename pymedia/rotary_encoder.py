#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import gpiod

import pymedia_redis
import pymedia_rotary_encoder

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

ROTARY_ENCODER_DISCARD_TIME_WINDOW = 0.1
ROTARY_ENCODER_MAX_AGE = 0.15

REDIS = None

# ----------------

def cdsp_set_volume(_1, _2, incr):
    """Send (publish) volume up/down actions for CamillaDSP."""
    REDIS.send_action('CDSP', f"set_volume:{incr}")


# ----------------

if __name__ == '__main__':

    gpiochip0 = gpiod.Chip("gpiochip0")

    REDIS = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'ROTARY_ENCODER')

    vol_event = pymedia_rotary_encoder.ProcessEvent(cdsp_set_volume,
                                      ROTARY_ENCODER_DISCARD_TIME_WINDOW,
                                      ROTARY_ENCODER_MAX_AGE)

    r_enc = pymedia_rotary_encoder.RotaryEncoder(gpiochip0, 16, 15,
                                             callback=vol_event.event,
                                             threaded_callback=True)

    r_enc.wait_events()
