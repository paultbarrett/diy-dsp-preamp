#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import time
import threading
import gpiod
import pymedia_logger

# ---------------------

DEBOUNCE_DELAY = 0.02
HELD_TIME = 2

# ----------------

class Gpio():
    """Generic libgpiod class."""
    def __init__(self,
                 gpiochip,
                 pin,
                 gpio_type,
                 consumer,
                 default_value=0,
                 pullup=False,
                 ):
        self._log = pymedia_logger.get_logger(__class__.__name__,
                                              f"[{gpiochip.name()}:{pin}]")
        self._log.debug("Initializing")

        try:
            self._line = gpiochip.get_line(pin)

            if gpio_type == gpiod.LINE_REQ_DIR_OUT:
                self._line.request(consumer=consumer, type=gpio_type,
                                   default_val=default_value)
            else:
                self._line.request(consumer=consumer, type=gpio_type)
                if default_value:
                    self._log.warning("Not setting default_val for inputs")

            self._line.get_value()  # make sure this works
        except Exception as ex:
            self._log.error(ex)
            raise SystemExit from ex

        self._pullup = pullup

    def get_value(self):
        """Get current value, unmodified."""
        try:
            return self._line.get_value()
        except Exception as ex:
            self._log.error(ex)
            raise SystemExit from ex

    def get_bool_state(self):
        """Get current digital state (boolean), inversed if pullup=True."""
        return bool(self.get_value()) ^ self._pullup


class DigitalInputPinEvent(Gpio):
    """Event/interrupt based digital input class."""
    def __init__(self,
                 gpiochip,
                 pin,
                 pullup=False,
                 cb_pressed=None,
                 cb_pressed_args=(),
                 cb_held=None,
                 cb_held_args=(),
                 debounce_delay=DEBOUNCE_DELAY,
                 held_time=HELD_TIME,
                 consumer="pymedia"
                 ):
        super().__init__(gpiochip, pin, gpiod.LINE_REQ_EV_BOTH_EDGES, consumer,
                         pullup=pullup)

        self._log = pymedia_logger.get_logger(__class__.__name__,
                                              f"[{gpiochip.name()}:{pin}]")
        if not cb_pressed and not cb_held:
            raise Exception("no pressed/held callback defined !")

        self._cb_pressed = cb_pressed
        self._cb_pressed_args = cb_pressed_args
        self._cb_held = cb_held
        self._cb_held_args = cb_held_args

        self._held_time = held_time

        self.th_wait = threading.Thread(target=self._wait_input,
                                        args=(debounce_delay,))
        self.th_wait.daemon = True
        self._cb_held_thread_ev = threading.Event()

        self._cb_held_complete = False

    def _run_cb_held_timer(self):
        """Start a "input held" callback timer."""
        self._cb_held_complete = False
        cancel = self._cb_held_thread_ev.wait(self._held_time)
        # run callback if the task wasn't "cancelled" ; the input shouldn't be
        # released by the time the timer expires
        if self.get_bool_state() and not cancel:
            self._log.debug("running callback_held")
            self._cb_held_complete = True
            self._cb_held(*self._cb_held_args)
        else:
            self._log.debug("input was released while waiting or thread was"
                          " cancelled - won't run callback")

    def _wait_input(self, debounce_delay):
        """Loop / run callbacks on pin change (interrupt based).

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

            # with a pull down, falling edge->0, rising->1 (ie. '0' at rest)
            # values are reversed with a pull up (ie. '1' at rest)
            if event.type == gpiod.LineEvent.FALLING_EDGE:
                activated = False ^ self._pullup
                self._log.debug("Falling Edge")
            elif event.type == gpiod.LineEvent.RISING_EDGE:
                activated = True ^ self._pullup
                self._log.debug("Rising Edge")
            else:
                raise TypeError('Invalid event type')

            # it shouldn't be possible to receive two consecutive event types
            # (eg. "Falling edge" then "Falling edge" again) yet this often
            # happens. HW or SW bug ?
            if last_event == event.type:
                self._log.debug("Last event type was repeated - skipping")
                continue
            last_event = event.type

            if time.time() - last_valid_event_time < debounce_delay:
                self._log.debug("button event within %ss - ignoring",
                             debounce_delay)
                continue
            last_valid_event_time = time.time()

            run_cb_pressed = False
            run_cb_held = False

            if activated:
                self._log.debug("input activated")
                if self._cb_held:
                    if cb_held_thread and cb_held_thread.is_alive():
                        self._log.debug("cb_held thread already started -"
                                      "bounce ?")
                        continue
                    run_cb_held = True
                elif self._cb_pressed:
                    run_cb_pressed = True

            else:
                self._log.debug("input deactivated")
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


class DigitalOutputPin(Gpio):
    """Digital output class."""
    def __init__(self, gpiochip, pin, default_value=0,
                 consumer="pymedia"):
        super().__init__(gpiochip, pin, gpiod.LINE_REQ_DIR_OUT, consumer,
                         default_value=default_value)

        self._log = pymedia_logger.get_logger(__class__.__name__,
                                              f"[{gpiochip.name()}:{pin}]")

    def set_value(self, value):
        """Set digital output."""
        try:
            self._line.set_value(value)
        except Exception as ex:
            self._log.error("Error: %s", ex)
            raise SystemExit from ex

    def blink(self, interval=1):
        """Blink output (blocking function)."""
        while True:
            self.set_value(0)
            time.sleep(interval)
            self.set_value(1)
            time.sleep(interval)
