# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import os
import time

from camilladsp import CamillaConnection, CamillaError, ProcessingState

import pymedia_logger
from pymedia_utils import SimpleThreads

logger = pymedia_logger.get_logger(__name__)

# ---------------------

class CDsp():
    """ Helper class to manage a CamillaDSP instance.

    sample config passed as argument in init():

    cfg = {
        'server': 'localhost',
        'port': 1234,
        'volume_min': -60,
        'volume_max': -12,
        'volume_step': 1,
        # the following are optional
        'update_interval': 4,
        'config_path': os.environ.get('HOME') + "/camilladsp/configs",
        'config_mute_on_change': True,
        'configs': (
                "M4_streamer_loop0.yml",
                "M4_streamer_loop1.yml",
                ),
        'configs_control_player': (
                True,
                False,
                ),
        }
    """

    def __init__(self, cfg, _redis = None):
        self._log = pymedia_logger.get_logger(__class__.__name__)
        self._cfg = cfg
        self._redis = _redis
        self._setting_volume = False
        self._switching_config = False
        self._cdsp = None
        self._config_index = 0
        self._stats = {}

        self._check_cfg()
        self.threads = SimpleThreads()
        self.threads.add_target(self.connect_loop)
        if self._cfg.get('update_interval'):
            self.threads.add_target(self.update_loop)
        if self._redis:
            self.threads.add_thread(self._redis.t_wait_action(self.action))

    def _check_cfg(self):
        if self._cfg.get('configs') and not self._cfg.get('update_interval'):
            raise Exception("cfg: 'configs' is set but not 'update_interval'")
        for param in [
                'server',
                'port',
                'volume_min',
                'volume_max',
                'volume_step'
                ]:
            if not self._cfg.get(param):
                raise Exception(f"Configuration parameter '{param}' isn't defined")

    def connect_loop(self):
        """Connect to CamillaDSP (loop).

        Keep trying to connect to CamillaDSP, and upon connection update stats,
        wake-up sub, etc.

        Blocking, executed from within a thread (self.t_connect_loop)
        """
        self._cdsp = CamillaConnection(self._cfg['server'],
                                       self._cfg['port'])
        connect_attempts = 0
        connected = False
        while True:
            if not self._cdsp.is_connected():
                try:
                    self._cdsp.connect()
                except (ConnectionRefusedError, CamillaError, IOError) as ex:
                    # log (debug) every time, but log (info) once
                    self._log.debug("Couldn't connect to CamillaDSP: %s", ex)
                    if connect_attempts == 0:
                        self._log.info("Couldn't connect to CamillaDSP")
                    connect_attempts += 1
                    if self._redis:
                        self._redis.set("is_on", False)
                        # turn off player if we're not connected
                        if (self._redis.check_alive('PLAYER')
                            and self._redis.get_s("PLAYER:power")
                            and connected):
                            self._redis.send_action('PLAYER', "off")
                    connected = False
                else:
                    connect_attempts = 0
                    connected = True
                    self._log.info("Connected to CamillaDSP on %s:%d"
                                  " - version:%s", self._cfg['server'],
                                   self._cfg['port'],
                                  self._cdsp.get_version()
                                  )
                    self.update()
                    if self._redis:
                        # wake up subwoofer with inaudible lfe tone
                        self._redis.send_action('LFE_TONE',
                                               "play_skip_tests")

            time.sleep(2)


    def is_on(self):
        """Check if CamillaDSP is active.

        Active: we're connected and CamillaDSP is running or paused
        """
        try:
            if (self._cdsp and self._cdsp.is_connected()
                and self._cdsp_wp("get_state") in [ ProcessingState.RUNNING,
                                             ProcessingState.PAUSED ]):
                return True
        except (ConnectionRefusedError, CamillaError, IOError) as ex:
            self._log.warning("Exception: %s", ex)

        return False

    def action(self, action=""):
        """Run user actions.

        This function is usually called by a loop waiting for user actions
        published (sent) via redis.
        """

        if not self.is_on():
            return

        # 'volume_incr:4'
        # 'volume_incr:-2'
        if action.startswith("volume_incr:"):
            func_action = self.set_volume_incr
            func_action_args = (float(action.split(':')[1]),)

        # 'volume_perc:50'
        # 'volume_perc:+4'
        # 'volume_perc:-4:NO_PLAYER_VOL_UPDATE'
        elif action.startswith("volume_perc:"):
            a_split = action.split(':')
            s_val = a_split[1]
            if s_val.startswith('+') or s_val.startswith('-'):
                func_action = self.set_volume_percent_incr
            else:
                func_action = self.set_volume_percent
            player_vol_update = True
            try:
                if a_split[2] == "NO_PLAYER_VOL_UPDATE":
                    player_vol_update = False
            except IndexError:
                pass
            func_action_args = (float(s_val), player_vol_update)

        else:
            func_action, func_action_args = {

                    "toggle_mute": [self.mute, ("toggle",)],

                    "mute": [self.mute, ("mute",)],

                    "unmute": [self.mute, ("unmute",)],

                    "first_config": [self.load_config, (0,)],

                    "next_config": [self.load_next_config, ()],

                    }.get(action, [None, None])

        if not func_action:
            self._log.warning("action '%s' isn't defined", action)
            return

        self._log.info("'%s'", action)

        func_action(*func_action_args)


    def mute(self, mode="toggle"):
        """Mute/unmute/toggle mute.

        Also publish status in redis, wake-up sub on unmute, and publish an
        event to notify consumers (eg. display.py).
        """
        set_mute = True
        if mode == "toggle":
            if self._cdsp_wp("get_mute"):
                set_mute = False
        elif mode == "mute":
            pass
        elif mode == "unmute":
            set_mute = True
        else:
            self._log.warning("mode '%s' isn't defined", mode)
            return

        if set_mute:
            self._cdsp_wp("set_mute", True)
            if self._redis:
                self._redis.set("mute", True)
                self._redis.send_action('PLAYER', "pause")
                self._redis.publish_event("mute")
        else:
            self._cdsp_wp("set_mute", False)

            if not self._redis:
                return

            # wake up subwoofer
            self._redis.send_action('LFE_TONE', "play_skip_tests")

            if self._cfg.get('configs_control_player'):
                try:
                    if self._cfg['configs_control_player'][self._config_index]:
                        self._redis.send_action('PLAYER', "unpause")
                except IndexError:
                    self._log.error("No configs_control_player index"
                                    "defined at index %d",
                                    self._config_index)

            self._redis.set("mute", False)
            self._redis.publish_event("mute")

    def db_vol_to_perc_vol(self, vol_db):
        """Convert CamillaDSP volume in dB to [0-100]."""
        return ( 100 * (vol_db - self._cfg['volume_min'])
                    / (self._cfg['volume_max'] - self._cfg['volume_min']))

    def perc_vol_to_db_vol(self, vol_perc):
        """Convert a [0-100] volume to CamillaDSP volume in dB."""
        return ( (self._cfg['volume_max'] - self._cfg['volume_min'])
                * vol_perc / 100
                + self._cfg['volume_min'] )

    def set_volume_incr(self, vol_incr, player_vol_update=True):
        """Increment volume."""
        self.set_volume_db(self._cdsp_wp("get_volume")
                           + round(vol_incr * self._cfg['volume_step']),
                           player_vol_update)

    def set_volume_percent_incr(self, vol_perc_incr, player_vol_update=True):
        """Increment volume as a percentage of the volume range."""
        vol_db_incr = vol_perc_incr / 100 * (self._cfg['volume_max'] -
                                               self._cfg['volume_min'])
        self._log.debug("Conversion %s%% = %sdB", vol_perc_incr, vol_db_incr)
        self.set_volume_incr(vol_db_incr, player_vol_update)

    def set_volume_percent(self, vol_perc, player_vol_update=True):
        """Set volume as a percentage of the volume range."""
        vol_db = self.perc_vol_to_db_vol(vol_perc)
        self.set_volume_db(vol_db, player_vol_update)

    def set_volume_db(self, vol, player_vol_update=True):
        """Set volume as a (CamillaDSP) dB value."""
        # set vol to max/min if it's greater/lower than max/min
        if not (self._cfg['volume_min'] <= vol
                <= self._cfg['volume_max']):
            self._log.debug("volume '%s' is out of range", vol)
            vol = ( self._cfg['volume_max']
                   if vol > self._cfg['volume_max']
                   else self._cfg['volume_min']
                   )

        vol_i = round(vol)
        cur_vol = self._cdsp_wp("get_volume")
        self._log.debug("Setting volume to '%s' (current: %s)", vol, cur_vol)

        if round(cur_vol) == vol_i:
            self._log.debug("Current volume already %s", round(vol))
            return

        # avoid setting volume concurrently (possible as this task is run as
        # a thread)
        while self._setting_volume:
            self._log.debug("A volume change task is already running - wait")
            time.sleep(0.5)
        self._setting_volume = True
        self._cdsp_wp("set_volume", vol_i)
        self._setting_volume = False

        if self._redis:
            self._redis.set("volume", vol_i)
            # set/sync player volume
            if player_vol_update and self._cfg.get('configs_control_player'):
                vol_perc = round(self.db_vol_to_perc_vol(vol), 2)
                try:
                    if self._cfg['configs_control_player'][self._config_index]:
                        self._redis.send_action('PLAYER',
                                                f"volume_perc:{vol_perc}")
                except IndexError:
                    self._log.error("No configs_control_player index"
                                    "defined at index %d",
                                    self._config_index)
            self._redis.publish_event("volume")

    def load_next_config(self):
        self._log.info("Next config")
        index = (self._config_index + 1 ) % len(self._cfg['configs'])
        self.load_config(index)

    def load_config(self, index):
        """Load config in _cfg['configs'][]."""
        if not self._cfg.get('configs'):
            self._log.error("Trying to load next config but not config defined")
            return

        # avoid switching config concurrently (possible as this task is run as
        # a thread)
        while self._switching_config:
            self._log.info("A 'next config' task is already running - wait")
            time.sleep(0.5)

        try:
            config_path = (self._cfg.get('config_path') +
                           "/" + self._cfg['configs'][index])
        except IndexError:
            self._log.warning("Couldn't find user configuration for index %s",
                            index)
            return

        self._switching_config = True

        if index == self._config_index:
            self._log.info("Index hasn't changed - won't do anything")
        else:
            self._log.info("Reading and validating config file '%s'",
                          config_path)

            # immediate user feedback as read/validates takes a bit of time
            self._switching_config = True
            self._redis.set("switching_config", True)
            self._redis.publish_event("change config")

            if self._cfg.get('config_mute_on_change'):
                self.mute(mode="mute")

            try:
                config = self._cdsp.read_config_file(config_path)
                self._cdsp.validate_config(config)
                self._log.info("Loading config file in CamillaDSP")
                self._cdsp.set_config(config)
                self._cdsp.set_config_name(config_path)
                cur_config_path = self._cdsp.get_config_name()
            except CamillaError as ex:
                self._log.error("Can't load config into CamillaDSP: %s", ex)
            else:
                self._log.info("Current config is index %d, path '%s'",
                              index, cur_config_path)
                self._config_index = index

        self._switching_config = False
        self.update()

    def _cdsp_wp(self, func_name, *args, **kwargs):
        """Wrapper function to CamillaDSP functions.

        See https://github.com/HEnquist/pycamilladsp#reading-status
        """
        res = None
        func = getattr(self._cdsp, str(func_name))
        try:
            res = func(*args, **kwargs)
        except ConnectionRefusedError as ex:
            self._log.error(("Can't connect to CamillaDSP, is it running?"
                " Error: %s") , ex)
        except CamillaError as ex:
            self._log.error("CamillaDSP replied with error: %s", ex)
        except IOError as ex:
            self._log.error("Websocket is not connected: %s", ex)
        return res

    def update_loop(self):
        """Loop - Update stats every cfg['update_interval'] seconds.

        Blocking, executed from within a thread (self._t_update_loop)
        """
        while True:
            time.sleep(self._cfg['update_interval'])
            self.update()

    def update(self):
        """Update stats and update redis if they've changed."""
        is_on = self.is_on()
        if is_on:
            self._log.debug("Updating stats{}")

            if self._redis:
                self._redis.set_alive(wait_set = True)

            try:
                # update/sync the current config index
                cur_config_path = self._cdsp.get_config_name()
            except (ConnectionRefusedError, CamillaError, IOError) as ex:
                self._log.error(ex)
                return

            # update stats{}
            prev_stats = self._stats.copy()

            if self._cfg.get('configs'):
                try:
                    self._config_index = self._cfg['configs'].index(
                            os.path.basename(cur_config_path)
                            )
                    #self._log.debug("Found index is %d", index)
                except (IndexError, ValueError):
                    self._log.warning("Couldn't find active configuration (%s)"
                                      " in user configuration (%s)",
                                     cur_config_path, self._cfg['configs'])
                else:
                    self._stats['config_index' ] = self._config_index

                try:
                    self._stats['control_player'] = (
                        self._cfg['configs_control_player'][self._config_index])
                except (IndexError, KeyError) as ex:
                    self._log.warning("cfg['configs_control_player'] error: %s",
                                      ex)

            if self._redis:
                self._stats['volume'] = round(self._cdsp_wp("get_volume"))
                self._stats['max_playback_signal_rms'] = (
                        round(max(self._cdsp_wp("get_playback_signal_rms"))))
                self._stats['max_playback_signal_peak'] = (
                        round(max(self._cdsp_wp("get_playback_signal_peak"))))
                self._stats['is_on'] = is_on
                self._stats['mute'] = self._cdsp_wp("get_mute")
                self._stats['switching_config'] = self._switching_config

                # update redis and send 'change' action - if any
                if prev_stats != self._stats:
                    self._log.debug("stats have changed - updating redis")
                    self._log.debug(self._stats)
                    self._redis.update_stats(self._stats,
                                             send_data_changed_event = True)


def redis_cdsp_ping(redis_r, max_age=20):
    if not bool(redis_r.get_s("CDSP:is_on")):
        logger.debug("Cdsp isn't running")
        return False
    return redis_r.check_alive('CDSP', max_age)
