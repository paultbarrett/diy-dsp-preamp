# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import time

# LMS
import requests
import lmsquery

from pymedia_utils import logging, Log, SimpleThreads
from pymedia_cdsp import redis_cdsp_ping

# ---------------------

# https://github.com/elParaguayo/LMS-CLI-Documentation/blob/master/LMS-CLI.md

class Lms(metaclass=Log):
    def __init__(self, server, playerid, _redis, update_interval=4):
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
        self.threads = SimpleThreads()
        self.threads.add_target(self.update_loop, update_interval)
        self.threads.add_thread(self._redis.t_wait_action(self.action))

    def is_playing(self):
        """Return player 'isplaying' status."""
        return self._stats['isplaying']

    def update_loop(self, update_interval):
        """Loop - Update stats every update_interval seconds.

        Blocking, should be executed as a thread.
        """
        while True:
            time.sleep(update_interval)
            self.update()

    def action(self, action):
        """Run user actions.

        This function is usually called by a loop waiting for user actions
        published (sent) via redis.
        """
        if not self._lmsquery:
            logging.info("lms query isn't defined; player not running ?")
            return

        if "volume_perc:" in action:
            try:
                vol_perc = float(action.split('volume_perc:')[1])
            except ValueError as ex:
                logging.error(ex)
                return

            if not 0 <= vol_perc <= 100:
                logging.error("Volume is outside range: %d", vol_perc)
                return

            func_action = self._lmsquery.set_volume
            func_action_args = (vol_perc,)

        else:
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
            logging.warning("action '%s' isn't defined", action)
            return

        logging.info("'%s'", action)

        try:
            func_action(self._playerid, *func_action_args)
        except (requests.Timeout, requests.exceptions.ConnectionError) as ex:
            logging.warning(ex)
            return

        self.update()


    def update(self):
        """Update stats and update redis if they've changed."""
        logging.debug("updating info")

        self._redis.set_alive()

        if not redis_cdsp_ping(self._redis, max_age=10):
            # no use to refresh stuff if cdsp isn't on
            logging.debug("CDSP isn't running - won't refresh")
            return

        prev_stats = self._stats.copy()

        try:
            # https://stackoverflow.com/questions/8653516/python-list-of-dictionaries-search
            player = next((item for item in self._lmsquery.get_players()
                           if item["playerid"] == self._playerid), None)
        except (requests.Timeout, requests.exceptions.ConnectionError) as ex:
            logging.debug("Connection error: %s", ex)
            return

        if not player:
            # debug loglevel to avoid flooding logs when the player - eg.
            # squeezelite isn't running
            logging.debug("Player not found")
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
            logging.error(ex)
            return
        except (requests.Timeout, requests.exceptions.ConnectionError) as ex:
            logging.debug("Connection error: %s", ex)
            return

        # update redis even if stats haven't changed; it fixes rare corner case
        # where redis player keys and lms stats{} aren't synchronized
        self._redis.update_stats(self._stats)

        if prev_stats != self._stats:
            logging.debug("stats have changed - updating redis")
            logging.debug(self._stats)
            self._redis.publish_event("stats")
