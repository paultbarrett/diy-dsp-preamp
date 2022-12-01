#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import time
import subprocess
import os

import pymedia_redis
import pymedia_utils
from pymedia_cdsp import redis_cdsp_ping

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

# inaudible tones used to "wake up" the subwoofer
#
# Keep sample rate / format in sync with /etc/asound.conf and CamillaDSP
# configuration !
#
# Alternatively we could use the same tone file and use alsa's "plug" plugin to
# play with the right rate/format; a potential issue is that aplay could open
# the device with different sample rate/format/channels params if camilladsp
# isn't running yet.
# 'plug' also fixes IPC permission issues if they aren't set properly
# Note: CPU usage is the same when using hw: or plug: device, despite alsa
# re-sampling stuff.
#
# Generating tones:
# - audacity (generate / tone / ...)
# - or sox (see ~/sounds/gen_tone)

LFE_TONE_DEFS = [
        # confix index 0
        {
            'file' : (os.environ.get('HOME')
                      + "/sounds/tone_mono_6Hz_10s_44100_signed16.wav"),
            'device' : "Loopback0_0_c2",
            },
        # confix index 1
        {
            'file' : (os.environ.get('HOME')
                      + "/sounds/tone_mono_6Hz_10s_24000_float32.wav"),
            'device' : "Loopback1_0_c2",
            },
        # confix index 2
        {
            'file' : (os.environ.get('HOME')
                      + "/sounds/tone_mono_6Hz_10s_44100_signed16.wav"),
            'device' : "Loopback2_0_c2",
            },

        ]

# how often the tone should be played (in seconds) when conditions are met
LFE_TONE_PLAY_INTERVAL = 240

LFE_TONE_PLAY_LOOP_INTERVAL = 10 # seconds

# ---------------------
class LfeTone():
    def __init__(self, _redis):
        self._log = logging.getLogger(self.__class__.__name__)
        self._redis = _redis
        self._playing_lfe_tone = False
        self._last_played_lfe_tone = self._redis.get_s("LFE_TONE:last_played")
        if self._last_played_lfe_tone is None:
            self._last_played_lfe_tone = 0
        self.threads = pymedia_utils.SimpleThreads()
        self.threads.add_target(self.loop_play)
        self.threads.add_thread(self._redis.t_wait_action(self.action))

    def action(self, action):
        """Run user actions.

        This function is usually called by a loop waiting for user actions
        published (sent) via redis.
        """
        if action == "play":
            self.play()
        elif action == "play_skip_tests":
            self.play(skip_tests = True)
        else:
            self._log.warning("action '%s' isn't defined", action)

    def loop_play(self):
        """Regularly run self.play() to play a lfe tone."""
        while True:
            reltime_last_played = time.time() - self._last_played_lfe_tone
            self._log.debug("last tone played %ds ago ; interval: %ds",
                           reltime_last_played, LFE_TONE_PLAY_INTERVAL)
            if reltime_last_played > LFE_TONE_PLAY_INTERVAL:
                self.play()
            time.sleep(LFE_TONE_PLAY_LOOP_INTERVAL)

    def play(self, skip_tests = False):
        """Play a lfe tone."""
        # pylint: disable=too-many-return-statements
        self._log.debug("playing LFE tone")

        # mandatory tests
        if time.time() - self._last_played_lfe_tone < LFE_TONE_PLAY_INTERVAL:
            self._log.debug("already played a tone within %d seconds - noop",
                           LFE_TONE_PLAY_INTERVAL)
            return

        if self._playing_lfe_tone:
            self._log.info("already playing lfe tones - noop")
            return

        # avoid keeping the subwoofer on when not needed
        if not skip_tests:

            if not redis_cdsp_ping(self._redis, max_age=10):
                self._log.debug("cdsp isn't on - noop")
                return

            if self._redis.get_s("CDSP:mute"):
                self._log.debug("cdsp is muted - noop")
                return

            if (self._redis.get_s("CDSP:control_player")
                and not self._redis.get_s("PLAYER:isplaying")):
                self._log.debug("cdsp controls player and player is paused - noop")
                return

        # get current config index
        cdsp_config_index = self._redis.get_s("CDSP:config_index")
        if cdsp_config_index == "":
            self._log.error("Couldn't get cdsp config index")
            return

        # get corresponding tone
        try:
            lfe = LFE_TONE_DEFS[int(cdsp_config_index)]
        except KeyError as ex:
            self._log.error("No index %s found in LFE_TONE_DEFS: %s",
                           cdsp_config_index, ex)
            return

        # finally, try to play the tone
        self._log.info("start playing lfe tone %s for config index %s on %s",
                       lfe['file'], cdsp_config_index, lfe['device'])

        self._playing_lfe_tone = True
        try:
            sub = subprocess.run(['aplay', '-D', lfe['device'], lfe['file'] ],
                            check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as ex:
            self._log.error("Error: %s / cmd: %s / stderr: %s", ex, ex.cmd,
                           ex.stderr)
        except FileNotFoundError as ex:
            self._log.error(ex)
        else:
            self._last_played_lfe_tone = time.time()
            self._log.debug("command stdout: %s", sub.stdout)
            self._log.debug("command stderr: %s", sub.stderr)
            self._redis.set_s("LFE_TONE:last_played", self._last_played_lfe_tone)
            self._log.info("stopped playing tone")

        self._playing_lfe_tone = False


# ----------------

if __name__ == '__main__':

    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                       'LFE_TONE')

    lfe_tone = LfeTone(_redis)

    lfe_tone.threads.start()

    try:
        lfe_tone.threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
