#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

# a standalone CamillaDSP "remote volume" (no redis, no display, etc.)

import gpiod

import pymedia_rotary_encoder
import pymedia_cdsp

# ---------------------

ROTARY_ENCODER_DISCARD_TIME_WINDOW = 0.1
ROTARY_ENCODER_MAX_AGE = 0.15

CDSP_CFG = {
        'server': 'localhost',
        'port': 1234,
        'volume_min': -60,
        'volume_max': -12,
        'volume_step': 1,
        }

CDSP = None

# ----------------

def cdsp_set_volume(_1, _2, incr):
    CDSP.incr_volume(incr)

# ----------------

if __name__ == '__main__':

    CDSP = pymedia_cdsp.CDsp(CDSP_CFG)

    gpiochip0 = gpiod.Chip("gpiochip0")

    vol_event = pymedia_rotary_encoder.ProcessEvent(cdsp_set_volume,
                                            ROTARY_ENCODER_DISCARD_TIME_WINDOW,
                                            ROTARY_ENCODER_MAX_AGE)

    gpiochip0 = gpiod.Chip("gpiochip0")
    r_enc = pymedia_rotary_encoder.RotaryEncoder(gpiochip0, 16, 15,
                                             callback=vol_event.event,
                                             threaded_callback=True)

    # for simplicity add rotary encoder wait_events() loop to CDSP's list of
    # threads
    CDSP.threads.add_target(r_enc.wait_events)

    CDSP.threads.start()

    try:
        CDSP.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
