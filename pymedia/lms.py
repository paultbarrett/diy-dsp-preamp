#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import pymedia_redis
import pymedia_lms

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

LMS_SERVER = "juke"
LMS_PLAYERID = "13:89:0e:c8:1d:a5"

# ---------------------

if __name__ == '__main__':

    # register as PLAYER
    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                       'PLAYER')

    lms = pymedia_lms.Lms(LMS_SERVER, LMS_PLAYERID, _redis)

    lms.threads.start()

    try:
        lms.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
