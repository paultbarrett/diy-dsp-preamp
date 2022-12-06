#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import threading
import gpiod

from pymedia_utils import logging, Log

# Software debouncing based on
# https://github.com/buxtronix/arduino/tree/master/libraries/Rotary

R_START = 0x0
R_CW_FINAL = 0x1
R_CW_BEGIN = 0x2
R_CW_NEXT = 0x3
R_CCW_BEGIN = 0x4
R_CCW_FINAL = 0x5
R_CCW_NEXT = 0x6

DIR_CW = 0x10   # Clockwise step.
DIR_CCW = 0x20  # Counter-clockwise step.

# Translation table (see buxtronix doc)
ttable = [
    # R_START
    [R_START,    R_CW_BEGIN,  R_CCW_BEGIN, R_START],
    # R_CW_FINAL
    [R_CW_NEXT,  R_START,     R_CW_FINAL,  R_START | DIR_CW],
    # R_CW_BEGIN
    [R_CW_NEXT,  R_CW_BEGIN,  R_START,     R_START],
    # R_CW_NEXT
    [R_CW_NEXT,  R_CW_BEGIN,  R_CW_FINAL,  R_START],
    # R_CCW_BEGIN
    [R_CCW_NEXT, R_START,     R_CCW_BEGIN, R_START],
    # R_CCW_FINAL
    [R_CCW_NEXT, R_CCW_FINAL, R_START,     R_START | DIR_CCW],
    # R_CCW_NEXT
    [R_CCW_NEXT, R_CCW_FINAL, R_CCW_BEGIN, R_START],
    ]


class RotaryEncoder(metaclass=Log):
    """Manage a rotary encoder with libgpiod."""

    def __init__(self, gpiochip, pin1, pin2, callback, invert=False,
                 threaded_callback=False):
        self._gpiochip = gpiochip
        self._pin1 = pin1
        self._pin2 = pin2
        self._value = 0
        self._direction = None
        self._pinstate = R_START
        self._invert = invert
        self._callback = callback
        self._threaded_callback = threaded_callback

    def value(self):
        return self._value

    def wait_events(self):
        """Wait and process pin1/pin2 changes (interrupts).

        Should be run in a thread if this script does other (blocking) things.
        """
        lines = self._gpiochip.get_lines([self._pin1, self._pin2])
        lines.request(consumer="wait_events", type=gpiod.LINE_REQ_EV_BOTH_EDGES)

        val = {}
        val[self._pin1] = 0
        val[self._pin2] = 0

        try:
            while True:
                ev_lines = lines.event_wait(sec=1)
                if not ev_lines:
                    continue

                valid_event = False
                for line in ev_lines:
                    event = line.event_read()
                    if event.type == gpiod.LineEvent.RISING_EDGE:
                        val[event.source.offset()] = 1
                        valid_event = True
                    elif event.type == gpiod.LineEvent.FALLING_EDGE:
                        val[event.source.offset()] = 0
                        valid_event = True
                    else:
                        raise TypeError('Invalid event type')

                if valid_event:
                    self._process(val[self._pin1], val[self._pin2])
        except KeyboardInterrupt:
            return

    def _run_callback(self):
        """Run self._callback function (optionally in a thread)."""
        if self._callback is not None:
            logging.debug("running callback | val:%s | thread: %s",
                            self._value, self._threaded_callback)
            direction = 1 if self._direction == DIR_CW else -1
            if self._threaded_callback:
                thread = threading.Thread(target=self._callback,
                                          args=(self._value, direction))
                thread.daemon = True
                thread.start()
            else:
                self._callback(self._value, direction)


    def _process(self, pin1_val, pin2_val):
        pinstate = (pin1_val << 1) | pin2_val

        if self._invert:
            pinstate = ~pinstate & 0x03

        self._pinstate = ttable[self._pinstate & 0xf][pinstate]
        direction = self._pinstate & 0x30

        prev_value = self._value
        if direction == DIR_CW:
            self._value += 1
            self._direction = DIR_CW
        elif direction == DIR_CCW:
            self._value += -1
            self._direction = DIR_CCW

        if prev_value != self._value:
            self._run_callback()
