#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import time
import threading

import gpiod

from pymedia_utils import logging, Log, LOGFORMAT, LOGFORMAT_DATE

# ---------------------

DEBOUNCE_DELAY = 0.02
HELD_TIME = 2

# ----------------

class DigitalInputPin(metaclass=Log):

    def __init__(self,
                 gpiochip,
                 pin,
                 cb_pressed=None,
                 cb_pressed_args=(),
                 cb_held=None,
                 cb_held_args=(),
                 threaded_callback=False,
                 debounce_delay=DEBOUNCE_DELAY,
                 held_time=HELD_TIME,
                 ):

        # overly complex way to change the logger format to display the
        # gpiochip/pin to help debugging
        self._log = logging.getLogger()
        handler = logging.StreamHandler()
        formatter = logging.Formatter(f"{LOGFORMAT} ({gpiochip.name()}:{pin})",
                                      datefmt=LOGFORMAT_DATE)
        handler.setFormatter(formatter)
        self._log.handlers = []    # logger.propagate = False
        self._log.addHandler(handler)

        logging.debug("Initializing")

        if not cb_pressed and not cb_held:
            raise Exception("no pressed/held callback defined !")

        try:
            if gpiochip is None:
                self._log.error("gpiochip not found")
                raise SystemExit
            self._line = gpiochip.get_line(pin)
            self._line.request(consumer="wait_events",
                               type=gpiod.LINE_REQ_EV_BOTH_EDGES)
        except Exception as ex:
            self._log.error("Error: %s", ex)
            raise SystemExit from ex

        self._cb_pressed = cb_pressed
        self._cb_pressed_args = cb_pressed_args
        self._cb_held = cb_held
        self._cb_held_args = cb_held_args

        self._threaded_callback = threaded_callback
        self._held_time = held_time

        self.th_wait = threading.Thread(target=self._wait_input,
                                        args=(debounce_delay,))
        self.th_wait.daemon = True
        self._cb_held_thread_ev = threading.Event()

        self._cb_held_complete = False

        self._label = f"{gpiochip.name()}:{pin}"

    def get_value(self):
        return self._line.get_value()

    def _run_cb_held_timer(self):
        self._cb_held_complete = False
        cancel = self._cb_held_thread_ev.wait(self._held_time)
        # run callback if the task wasn't "cancelled" ; the input shouldn't be
        # released by the time the timer expires (0: button is pressed)
        if self.get_value() == 0 and not cancel:
            self._cb_held_complete = True
            self._cb_held(*self._cb_held_args)
        else:
            self._log.debug("input was released while waiting or thread was"
                          " cancelled - won't run callback")

    def _wait_input(self, debounce_delay):
        """Loop / run callback on pin change (interrupt based).

        Blocking - should be run in a thread.
        """
        last_valid_event_time = 0
        last_event = None

        cb_pressed_thread = None
        cb_held_thread = None

        while True:
            ev_line = self._line.event_wait(sec=1)
            if not ev_line:
                continue

            event = self._line.event_read()

            # with a pull up, at rest a gpio's value is 1
            # -> FALLING_EDGE: the input was activated (ie. button pressed)
            # -> RISING_EDGE: the input was deactivated (ie. button released)

            if event.type == gpiod.LineEvent.FALLING_EDGE:
                self._log.debug("Falling edge - value is True")
                pressed = True
            elif event.type == gpiod.LineEvent.RISING_EDGE:
                self._log.debug("Rising Edge - value is False")
                pressed = False
            else:
                raise TypeError('Invalid event type')

            # it shouldn't be possible to receive two consecutive event types
            # (eg. "Falling edge" then "Falling edge" again) yet this often
            # happens. HW or SW bug ?
            if last_event == event.type:
                self._log.debug("Last event type was identical - skipping")
                continue
            last_event = event.type

            if time.time() - last_valid_event_time < debounce_delay:
                self._log.debug("button event %s edge within %ss - ignoring",
                             "Falling" if pressed else "Rising",
                             debounce_delay)
                continue
            last_valid_event_time = time.time()

            run_cb_pressed = False
            run_cb_held = False

            if pressed:
                self._log.debug("input activated %s", self._label)
                if self._cb_held:
                    if cb_held_thread and cb_held_thread.is_alive():
                        self._log.debug("cb_held thread already started -"
                                      "bounce ?")
                        continue
                    run_cb_held = True
                elif self._cb_pressed:
                    run_cb_pressed = True

            else:
                self._log.debug("input deactivated, %s", self._label)
                # cancel a cb_held task if running
                if self._cb_held:
                    if cb_held_thread and cb_held_thread.is_alive():
                        self._log.debug("Cancelling cb_held thread")
                        self._cb_held_thread_ev.set()
                        self._cb_held_thread_ev.clear()

                    if self._cb_pressed and not self._cb_held_complete:
                        if cb_pressed_thread and cb_pressed_thread.is_alive():
                            self._log.debug("cb_pressed thread already started")
                        else:
                            run_cb_pressed = True

            if run_cb_pressed:
                self._log.debug("Starting cb_pressed thread")
                cb_pressed_thread = threading.Thread(target=self._cb_pressed,
                                                     args=self._cb_pressed_args)
                cb_pressed_thread.daemon = True
                cb_pressed_thread.start()

            if run_cb_held:
                self._log.debug("Starting cb_held timer thread")
                cb_held_thread = threading.Thread(
                        target=self._run_cb_held_timer)
                cb_held_thread.daemon = True
                cb_held_thread.start()


class DigitalOutputPin(metaclass=Log):
    def __init__(self, gpiochip, pin, default_value=0):
        logging.debug("Initializing %s:%s", gpiochip.name(), pin)
        try:
            if gpiochip is None:
                logging.error("gpiochip not found")
                raise SystemExit
            self._line = gpiochip.get_line(pin)
            self._line.request(consumer="pymedia", type=gpiod.LINE_REQ_DIR_OUT,
                               default_val=default_value)
        except Exception as ex:
            logging.error("Error: %s", ex)
            raise SystemExit from ex

    def set_value(self, level=0):
        """Set output."""
        try:
            if level:
                self._line.set_value(1)
            else:
                self._line.set_value(0)
        except Exception as ex:
            logging.error("Error: %s", ex)
            raise SystemExit from ex

    def get_value(self):
        """Get current output value."""
        try:
            return self._line.get_value()
        except Exception as ex:
            logging.error("Error: %s", ex)
            raise SystemExit from ex

    def blink(self, interval=1):
        """Blink output (blocking function)."""
        while True:
            self.set_value(0)
            time.sleep(interval)
            self.set_value(1)
            time.sleep(interval)
