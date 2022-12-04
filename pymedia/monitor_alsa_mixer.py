#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from pyalsa import alsamixer

import pymedia_alsa
import pymedia_redis
import pymedia_buffer_event

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

ALSA_PCM_CARD = "hw:CARD=Dummy" # get names with `aplay -L`
ALSA_PCM_NAME = "Master"        # find out with alsamixer -c ...

# get limits with `amixer -c... sget "Master"`
ALSA_MIN_VOL = -50
ALSA_MAX_VOL = 100

VOL_CHANGE_DISCARD_TIME_WINDOW = 0.1
VOL_CHANGE_MAX_AGE = 0.15


# test with:
# amixer -c... sset "Master" 80
# amixer -c... sset "Master" 79
# ...

# ---------------------

VOL_EVENT = None

def get_volume(mixer_element):
    vol_perc = ((mixer_element.get_volume() - ALSA_MIN_VOL)
            / (ALSA_MAX_VOL - ALSA_MIN_VOL) * 100)
    VOL_EVENT.event(int(vol_perc))

def cdsp_set_volume(vol, _direction, _incr):
    REDIS.send_action('CDSP', f"set_volume_perc:{vol}")


# ---------------------

if __name__ == '__main__':

    REDIS = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'ALSA_VOL')

    VOL_EVENT = pymedia_buffer_event.ProcessEvent(cdsp_set_volume,
                                              VOL_CHANGE_DISCARD_TIME_WINDOW,
                                              VOL_CHANGE_MAX_AGE)

    try:
        pymedia_alsa.poll(ALSA_PCM_CARD, ALSA_PCM_NAME, get_volume,
                          threaded_callback=True)
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
