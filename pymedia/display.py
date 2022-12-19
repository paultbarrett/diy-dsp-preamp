#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import pymedia_redis
import pymedia_display

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

if __name__ == '__main__':

    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                       'DISPLAY')

    display = pymedia_display.Display(_redis, pubsubs=(
        'PLAYER:EVENT',
        'CDSP:EVENT',
        ))

    display.t_wait_events.start()

    try:
        display.t_wait_events.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
        display.blank()
