# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import select
import logging
from pyalsa import alsamixer

# https://www.alsa-project.org/alsa-doc/alsa-lib/

# test with
# amixer -c1 sset "Master" 80
# amixer -c1 sset "Master" 79
# amixer -c1 sset "Master" 80
# ...

def poll(pcm, pcm_name, callback):

    mixer = alsamixer.Mixer()
    mixer.attach(pcm)
    mixer.load()

    alsa = alsamixer.Element(mixer, pcm_name)

    mixer.handle_events()

    poller = select.poll()
    mixer.register_poll(poller)

    while True:
        poller.poll()
        mixer.handle_events()
        logging.debug("Poll OK")
        callback(alsa)
