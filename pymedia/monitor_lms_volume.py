#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import socket
import re
from urllib.parse import unquote

import pymedia_redis
import pymedia_logger

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

logger = pymedia_logger.get_logger(__name__)

# ---------------------

LMS_SERVER = "juke"
LMS_SERVER_PORT = 9090
LMS_PLAYERID = "13:89:0e:c8:1d:a5"

# ---------------------

def cdsp_set_volume(vol, _redis):
    """Set CamillaDSP volume via redis action."""
    # Pass 'NO_PLAYER_VOL_UPDATE' to avoid potential "feedback loops";
    # otherwise pymedia_cdsp would update LMS' volume when receiving a volume
    # change action - if volumes aren't identical (eg. because of different
    # implementations of volume change in LMS and pymedia_cdsp) then there would
    # be an infinite back-and-forth.
    logger.info("Action - set CDSP volume to %s", vol)
    _redis.send_action('CDSP', f"volume_perc:{vol}:NO_PLAYER_VOL_UPDATE")

def receive_volume_event(_socket, player_id, callback, cb_args=()):

    # sample (we use unquote() to convert %3A to ':'):
    # 13%3A89%3A0e%3Ac8%3A1d%3Aa5 mixer volume 50
    # 13%3A89%3A0e%3Ac8%3A1d%3Aa5 mixer volume +5
    # ->
    # 13:89:0e:c8:1d:a5 mixer volume 60
    # 13:89:0e:c8:1d:a5 mixer volume -5
    regex = re.compile("^" + player_id + r" mixer volume ([+\-]?\d+)$")

    # "subscribe" to LMS volume changes
    _socket.send("subscribe mixer\r".encode("UTF-8"))

    while True:
        data = _socket.recv(4096)
        line = unquote(data.decode("UTF-8").strip())
        logger.debug("received %s", line)
        re_match = regex.match(line)
        if re_match:
            vol = re_match.group(1)
            logger.info("Volume changed to %s for player %s", vol,
                         LMS_PLAYERID)
            callback(vol, *cb_args)


# ---------------------

if __name__ == '__main__':

    redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'LMS_VOL')

    srvsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #srvsock.settimeout(3) # 3 second timeout on commands
    srvsock.connect((LMS_SERVER, LMS_SERVER_PORT))

    try:
        receive_volume_event(srvsock, LMS_PLAYERID, cdsp_set_volume,
                             cb_args=(redis,))
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
        srvsock.close()
