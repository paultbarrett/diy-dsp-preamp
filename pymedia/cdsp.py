#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import os

import pymedia_cdsp
import pymedia_redis

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

CDSP_CFG = {
        'server': 'localhost',
        'port': 1234,
        'volume_min': -60,
        'volume_max': -12,
        'volume_step': 1,
        'config_path': os.environ.get('HOME') + "/camilladsp/configs",
        'config_mute_on_change': True,
        'configs': (
            "M4_streamer_loop0.yml",
            "M4_streamer_loop1.yml",
            "M4_streamer_loop2.yml",
            ),
        'configs_control_player': (
            True,
            False,
            False,
            ),
        'update_interval': 4,
        }

# ---------------------

if __name__ == '__main__':

    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                       'CDSP')

    cdsp = pymedia_cdsp.CDsp(CDSP_CFG, _redis)

    cdsp.threads.start()

    try:
        cdsp.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
