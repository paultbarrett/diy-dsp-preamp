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

LMS_SUBSCRIBE = "mixer,playlist,play,pause,stop"

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

def parse_events(_socket, player_id, _redis):
    """Receive / parse events and trigger actions."""

    # sample (we use unquote() to convert %3A to ':'):
    # 13%3A89%3A0e%3Ac8%3A1d%3Aa5 mixer volume 50
    # 13%3A89%3A0e%3Ac8%3A1d%3Aa5 mixer volume -5
    # ->
    # 13:89:0e:c8:1d:a5 mixer volume 50
    # 13:89:0e:c8:1d:a5 mixer volume -5
    re_vol = re.compile("^" + player_id + r" mixer volume ([+\-]?\d+(\.\d+)?)$")

    while True:
        data = _socket.recv(4096)
        line = unquote(data.decode("UTF-8").strip())
        logger.debug("received %s", line)
        re_vol_match = re_vol.match(line)
        if re_vol_match:
            vol = re_vol_match.group(1)
            logger.info("Volume changed to %s for player %s", vol,
                         LMS_PLAYERID)
            cdsp_set_volume(vol, _redis)
        else:
            logger.debug("Action - PLAYER:update (received '%s')", line)
            _redis.send_action('PLAYER', "update")


# ---------------------

if __name__ == '__main__':

    redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'PLAYER_CHANNEL')

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #sock.settimeout(3) # 3 second timeout on commands
    sock.connect((LMS_SERVER, LMS_SERVER_PORT))

    try:
        sock.send(f"subscribe {LMS_SUBSCRIBE}\r".encode("UTF-8"))
        parse_events(sock, LMS_PLAYERID, redis)
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
        sock.close()
