#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from pyalsa import alsamixer

import pymedia_alsa
import pymedia_redis

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

ALSA_PCM_CARD = "hw:CARD=Dummy" # get names with `aplay -L`
ALSA_PCM_NAME = "Master"        # find out with alsamixer -c ...

# get limits with `amixer -c... sget "Master"`
ALSA_MIN_VOL = -50
ALSA_MAX_VOL = 100

# test with:
# amixer -c... sset "Master" 80
# amixer -c... sset "Master" 79
# ...

# ---------------------

def set_cdsp_vol(mixer_element):
    vol_perc = ((mixer_element.get_volume() - ALSA_MIN_VOL)
            / (ALSA_MAX_VOL - ALSA_MIN_VOL) * 100)
    print(vol_perc)
    REDIS.send_action('CDSP', f"set_volume_perc:{int(vol_perc)}")

# ---------------------

if __name__ == '__main__':

    REDIS = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'ALSA_VOL')

    try:
        pymedia_alsa.poll(ALSA_PCM_CARD, ALSA_PCM_NAME, set_cdsp_vol)
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
