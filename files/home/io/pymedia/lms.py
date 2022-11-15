#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import time

# LMS
import requests
import lmsquery

import pymedia

# ---------------------

LMS_SERVER = "juke"
LMS_PLAYERID = "13:89:0e:c8:1d:a5"
LMS_UPDATE_INTERVAL = 4 # seconds

# ---------------------

# https://github.com/elParaguayo/LMS-CLI-Documentation/blob/master/LMS-CLI.md

class Lms():
    def __init__(self, server, playerid, _redis):
        self._log = logging.getLogger(self.__class__.__name__)
        self._server = server
        self._lmsquery = lmsquery.LMSQuery(server)
        self._playerid = playerid
        self._redis = _redis
        self._stats = {
                'player_name' : '',
                'artist' : '',
                'title' : '',
                'isplaying' : False,
                'power' : False,
                }
        self.threads = pymedia.SimpleThreads()
        self.threads.add_target(self.update_loop)
        self.threads.add_thread(self._redis.t_wait_action(self.action))

    def is_playing(self):
        """Return player 'isplaying' status."""
        return self._stats['isplaying']

    def update_loop(self):
        """Loop - Update stats every LMS_UPDATE_INTERVAL seconds.

        Blocking, executed from within a thread (self.t_update_loop)
        """
        while True:
            time.sleep(LMS_UPDATE_INTERVAL)
            self.update()

    def action(self, action):
        """Run user actions.

        This function is usually called by a loop waiting for user actions
        published (sent) via redis.
        """
        if not self._lmsquery:
            self._log.info("lms query isn't defined; player not running ?")
            return

        func_action, func_action_args = {
                "previous_song": [self._lmsquery.previous_song, ()],
                "next_song": [self._lmsquery.next_song, ()],
                "play": [self._lmsquery.query, ("button", "play")],
                "stop": [self._lmsquery.query, ("button", "stop")],
                "pause": [self._lmsquery.query, ("pause", 1)],
                "unpause": [self._lmsquery.query, ("pause", 0)],
                "toggle_pause": [self._lmsquery.query, ("pause",)],
                "off": [self._lmsquery.query, ("power", 0)],
                "on": [self._lmsquery.query, ("power", 1)],
                "random_albums": [self._lmsquery.query, ("randomplay",
                                                        "albums")],
                "random_tracks": [self._lmsquery.query, ("randomplay",
                                                        "tracks")]
                }.get(action, [None, None])

        if not func_action:
            self._log.warning("action '%s' isn't defined", action)
            return

        self._log.info("'%s'", action)

        try:
            func_action(self._playerid, *func_action_args)
        except (requests.Timeout, requests.exceptions.ConnectionError) as ex:
            self._log.warning(ex)
            return

        self.update()


    def update(self):
        """Update stats and update redis if they've changed."""
        self._log.debug("updating info")

        self._redis.set_alive()

        if not pymedia.cdsp_ping(self._redis, max_age=10):
            # no use to refresh stuff if cdsp isn't on
            self._log.debug("CDSP isn't running - won't refresh")
            return

        prev_stats = self._stats.copy()

        try:
            # https://stackoverflow.com/questions/8653516/python-list-of-dictionaries-search
            player = next((item for item in self._lmsquery.get_players()
                           if item["playerid"] == self._playerid), None)
        except (requests.Timeout, requests.exceptions.ConnectionError) as ex:
            self._log.debug("Connection error: %s", ex)
            return

        if not player:
            # debug loglevel to avoid flooding logs when the player - eg.
            # squeezelite isn't running
            self._log.debug("Player not found")
            return

        try:
            self._stats['player_name'] = player["name"]
            self._stats['isplaying'] = bool(player["isplaying"])
            self._stats['power'] = bool(player["power"])

            if self._stats['isplaying']:
                self._stats['artist'] = (
                        self._lmsquery.get_current_artist(self._playerid))
                self._stats['album'] = (
                        self._lmsquery.get_current_album(self._playerid))
                self._stats['title'] = (
                        self._lmsquery.get_current_title(self._playerid))
        except KeyError as ex:
            self._log.error(ex)
            return
        except (requests.Timeout, requests.exceptions.ConnectionError) as ex:
            self._log.debug("Connection error: %s", ex)
            return

        # update redis even if stats haven't changed; it fixes rare corner case
        # where redis player keys and lms stats{} aren't synchronized
        self._redis.update_stats(self._stats)

        if prev_stats != self._stats:
            self._log.debug("stats have changed - updating redis")
            self._log.debug(self._stats)
            self._redis.publish_event("stats")



# ----------------

if __name__ == '__main__':

    # register as PLAYER
    _redis = pymedia.RedisHelper('PLAYER')

    lms = Lms(LMS_SERVER, LMS_PLAYERID, _redis)

    lms.threads.start()

    try:
        lms.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
