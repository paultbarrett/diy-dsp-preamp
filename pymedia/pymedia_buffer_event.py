# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import time

class ProcessEvent():
    def __init__(self, callback, discard_time_window=0.1, max_age=0.15):
        self._log = logging.getLogger(self.__class__.__name__)
        self._discard_time_window = discard_time_window
        self._max_age = max_age
        self._cur_event_id = 0
        self._last_event_time = 0
        self._last_event_value = None
        self._callback = callback

    def event(self, value, direction):
        """Process an event (like setting the volume).

        We're trying to avoid flooding the "receiver" (eg. camilladsp with
        volume change requests and/or the display with many refreshes) while
        still providing adequate feedback to the user; so:
        - run callback if the previous event is older than self._max_age
        - otherwise, wait for self._discard_time_window seconds then
          run callback if no new event has arrived meanwhile
        -> this means we may discard events, but we send the relative value, not
        just +1/-1 increments, so we don't loose data.

        Note: blocking (time.sleep()) so should be executed as a thread
        """
        self._cur_event_id += 1
        event_id = self._cur_event_id
        run_callback = False
        if time.time() - self._last_event_time > self._max_age:
            self._log.debug("thread id # %s: last event time was more than"
                          " %fs ago - running",
                          event_id, self._max_age)
            run_callback = True
        else:
            self._log.debug("thread id # %s: an event happened less than %fs"
                          " ago - waiting %fs to proceed", event_id,
                          self._max_age,
                          self._discard_time_window)
            time.sleep(self._discard_time_window)
            if event_id == self._cur_event_id:
                self._log.debug("thread id # %s: no new event - running",
                              event_id)
                run_callback = True
            else:
                self._log.debug("thread id # %s: event id %s took over",
                              event_id, self._cur_event_id)

        if run_callback:

            if self._last_event_value:
                incr = value - self._last_event_value
            else:
                incr = direction

            self._callback(value, direction, incr)
            self._last_event_value = value
            self._last_event_time = time.time()
