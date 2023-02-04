#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import socket
import re
from urllib.parse import unquote

import threading
import time

import pymedia_redis
import pymedia_logger

from pymedia_utils import SimpleThreads

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

logger = pymedia_logger.get_logger(__name__)

# ---------------------

LMS_SERVER = "juke"
LMS_SERVER_PORT = 9090
LMS_PLAYERID = "13:89:0e:c8:1d:a5"
LMS_SUBSCRIBE = "mixer,playlist,play,pause,stop"

LMS_PING_INTERVAL = 4    # MUST be less than LMS_SOCKET_TIMEOUT
LMS_SOCKET_TIMEOUT = 10

VOL_EVENT_KEYS = (
        'ROTARY_ENCODER:last_volume_event',
        )
VOL_EVENT_MAX_AGE = 2

# ---------------------

def cdsp_set_volume(_redis, vol):
    """Set CamillaDSP volume via redis action."""
    # don't update player volume if volume was changed by other means
    # within the last VOL_EVENT_MAX_AGE seconds
    for key in VOL_EVENT_KEYS:
        if _redis.check_timestamp(key, max_age=VOL_EVENT_MAX_AGE):
            logger.debug("Ignoring vol change: %s < %ss", key, VOL_EVENT_MAX_AGE)
            return

    # Pass 'NO_PLAYER_VOL_UPDATE' to avoid potential "feedback loops";
    # otherwise pymedia_cdsp would update LMS' volume when receiving a volume
    # change action - if volumes aren't identical (eg. because of different
    # implementations of volume change in LMS and pymedia_cdsp) then there would
    # be an infinite back-and-forth.
    logger.info("Action - set CDSP volume to %s", vol)
    _redis.send_action('CDSP', f"volume_perc:{vol}:NO_PLAYER_VOL_UPDATE")

def player_update_action(_redis):
    """Send a redis action to trigger a player stats update."""
    _redis.send_action('PLAYER', "update")

class LmsCliVol():
    def __init__(self, server, port, playerid,
                 f_vol, f_vol_args,
                 f_default, f_default_args,
                 ping_interval=LMS_PING_INTERVAL,
                 socket_timeout=LMS_SOCKET_TIMEOUT):

        self._log = pymedia_logger.get_logger(__class__.__name__)
        self.playerid = playerid
        self._redis = _redis

        self.f_vol = f_vol
        self.f_vol_args = f_vol_args

        self.f_default = f_default
        self.f_default_args = f_default_args

        self.th_ev_stop = threading.Event()

        self.threads = SimpleThreads()
        self.threads.add_target(self.ping, ping_interval)
        self.threads.add_target(self.parse_rcv)
        #self.threads.add_target(self.connect, server, port)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(socket_timeout)

        self._log.info("Connecting to %s:%s", server, port)
        try:
            self._sock.connect((server, port))
        except Exception as ex:
            self._log.error(ex)
            self.cleanup()
            raise SystemExit from ex

        self._log.info("Subscribing")
        self._sock.send(f"subscribe {LMS_SUBSCRIBE}\r".encode("UTF-8"))

        self.threads.start()

    def ping(self, ping_interval):
        """Ping (query version) at regular intervals."""
        while not self.th_ev_stop.is_set():
            self._log.info("ping")
            self._sock.send("version ?\r".encode("UTF-8"))
            time.sleep(ping_interval)

    def parse_rcv(self):
        """Receive / parse events and trigger actions."""

        # sample (we use unquote() to convert %3A to ':'):
        # 13%3A89%3A0e%3Ac8%3A1d%3Aa5 mixer volume 50
        # 13%3A89%3A0e%3Ac8%3A1d%3Aa5 mixer volume -5
        # ->
        # 13:89:0e:c8:1d:a5 mixer volume 50
        # 13:89:0e:c8:1d:a5 mixer volume -5
        re_vol = re.compile("^" + self.playerid
                            + r" mixer volume ([+\-]?\d+(\.\d+)?)$")

        while not self.th_ev_stop.is_set():

            try:
                data = self._sock.recv(4096)
            except Exception as ex:
                self._log.error(ex)
                self.cleanup()
                raise SystemExit from ex

            line = unquote(data.decode("UTF-8").strip())
            self._log.debug("received '%s'", line)

            if not line:
                self._log.error("Empty line received - connection closed ?")
                self.cleanup()
                raise SystemExit

            if line.startswith("subscribe") or line.startswith("version"):
                continue

            re_vol_match = re_vol.match(line)
            if re_vol_match:
                vol = re_vol_match.group(1)
                self._log.info("Volume changed to %s for player %s", vol,
                        LMS_PLAYERID)
                self.f_vol(self.f_vol_args, vol)
            else:
                self._log.info("Action - PLAYER:update (received '%s')", line)
                self.f_default(self.f_default_args)

    def cleanup(self):
        self.th_ev_stop.set()
        time.sleep(2)
        self._sock.close()



# ---------------------

if __name__ == '__main__':

    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'PLAYER_CHANNEL')

    lms_cli_vol = LmsCliVol(LMS_SERVER, LMS_SERVER_PORT, LMS_PLAYERID,
                            cdsp_set_volume, (_redis,),
                            player_update_action, (_redis)
                            )

    try:
        lms_cli_vol.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
        lms_cli_vol.cleanup()
