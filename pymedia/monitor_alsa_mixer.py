#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from pyalsa import alsamixer

import pymedia_alsa
import pymedia_redis
import pymedia_buffer_event

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ---------------------

ALSA_PCM_CARD = "hw:CARD=Dummy" # get names with `aplay -L`
ALSA_PCM_NAME = "Master"        # find out with alsamixer -c ...

# get limits with `amixer -c... sget "Master"`
ALSA_MIN_VOL = -50
ALSA_MAX_VOL = 100

VOL_CHANGE_DISCARD_TIME_WINDOW = 0.1
VOL_CHANGE_MAX_AGE = 0.15

# ---------------------

def get_volume(mixer_element, buffer_event):
    """Get volume from the alsa mixer, buffer/discard events."""
    vol_perc = ((mixer_element.get_volume() - ALSA_MIN_VOL)
            / (ALSA_MAX_VOL - ALSA_MIN_VOL) * 100)
    buffer_event.event(int(vol_perc))


def cdsp_set_volume(vol, _direction, _incr, _redis):
    """Set CamillaDSP and Player volume via redis action.

    _direction and _incr aren't used - those are passed by default by
    pymedia_buffer_event.ProcessEvent.event()

    only set CamillaDSP volume if CamillaDSP isn't muted to avoid "feedback
    loop": when cdsp is muted the lms player is paused (see pymedia_cdsp);
    however LMS and/or squeezelite set the mixer's volume to 0%, which trigger
    alsa mixer events, setting cdsp volume to 0%. Then, on "un-mute",
    LMS/squeezelite restores the mixer to its previous level, triggering another
    set of alsa mixer events and messing again with cdsp's volume.
    """
    if not _redis.get_s("CDSP:mute"):
        _redis.send_action('CDSP', f"volume_perc:{vol}")

# ---------------------

if __name__ == '__main__':

    # logic:
    #
    # pymedia_alsa.poll(): wait for a mixer event
    #  -> on event, call get_volume()
    #
    # get_volume(): calculate the volume %
    #  -> instead of immediately sending the volume change instructions, buffer
    #     events with pymedia_buffer_event.ProcessEvent.event()
    #
    # pymedia_buffer_event.ProcessEvent.event()
    #  -> calls cdsp_set_volume()
    #
    # cdsp_set_volume()
    #  -> send volume change "action" via redis

    # with this program running, test with:
    # amixer -c... sset "Master" 80
    # amixer -c... sset "Master" 79
    # ...

    redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'ALSA_VOL')

    buffer_vol_event = pymedia_buffer_event.ProcessEvent(cdsp_set_volume,
                                    VOL_CHANGE_DISCARD_TIME_WINDOW,
                                    VOL_CHANGE_MAX_AGE,
                                    cb_args=(redis,))

    try:
        pymedia_alsa.poll(ALSA_PCM_CARD, ALSA_PCM_NAME, get_volume,
                          threaded_callback=True, cb_args=(buffer_vol_event,))
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
