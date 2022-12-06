#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import pymedia_redis
import pymedia_display
from pymedia_cdsp import redis_cdsp_ping

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

def update_condition(_redis):
    if not redis_cdsp_ping(_redis, max_age=10):
        return False
    return True

# ---------------------

if __name__ == '__main__':

    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                       'DISPLAY')

    display = pymedia_display.Display(_redis,
                                      pubsubs=('PLAYER:EVENT', 'CDSP:EVENT'),
                                      f_condition=update_condition,
                                      f_condition_args=(_redis,)
                                      )
    display.draw_funcs = [ display.draw_status_bar, display.draw_cdsp_volume ]

    display.t_wait_events.start()

    try:
        display.t_wait_events.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
        display.blank()
