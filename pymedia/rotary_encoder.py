#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import gpiod

import pymedia_buffer_event
import pymedia_redis
import pymedia_rotary_encoder

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

ROTARY_ENCODER_DISCARD_TIME_WINDOW = 0.1
ROTARY_ENCODER_MAX_AGE = 0.15

# ----------------

def cdsp_set_volume(_1, _2, incr, _redis):
    """Send (publish) volume up/down actions for CamillaDSP."""
    _redis.send_action('CDSP', f"volume_incr:{incr}")


# ----------------

if __name__ == '__main__':

    gpiochip0 = gpiod.Chip("gpiochip0")

    redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'ROTARY_ENCODER')

    vol_event = pymedia_buffer_event.ProcessEvent(cdsp_set_volume,
                                      ROTARY_ENCODER_DISCARD_TIME_WINDOW,
                                      ROTARY_ENCODER_MAX_AGE,
                                      cb_args=(redis,))


    r_enc = pymedia_rotary_encoder.RotaryEncoder(gpiochip0, 16, 15,
                                             callback=vol_event.event,
                                             threaded_callback=True)

    r_enc.wait_events()
