#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import logging
import time
import threading

import gpiod

import pymedia

# ---------------------

BUTTON_PRESSED_DISCARD_TIME_WINDOW = 0.6

# unused (analog volume)
#GPIO_VOLUME_HIST = 50
#GPIO_VOLUME = "GPIO:a_in:volume_cdsp"

# ---------------------

REDIS = None

# ----------------

def wait_input_pin(gpiochip, pin, callback, threaded_callback=False,
                 timeout=BUTTON_PRESSED_DISCARD_TIME_WINDOW):
    """Loop / run callback on pin change (interrupt based).

    Blocking - should be run in a thread.
    """
    line = gpiochip.get_line(pin)
    # with a pull up, at rest a gpio's value is 1; falling edge indicates
    # the input was activated; use LINE_REQ_EV_RISING_EDGE otherwise
    line.request(consumer="wait_events",
                 type=gpiod.LINE_REQ_EV_FALLING_EDGE)

    last_press_time = 0

    while True:
        ev_line = line.event_wait(sec=1)
        if not ev_line:
            continue

        event = line.event_read()
        if event.type != gpiod.LineEvent.FALLING_EDGE:
            raise TypeError('Invalid event type')

        if time.time() - last_press_time < timeout:
            logging.info("button pressed within %ds - ignoring",
                         timeout)
            continue

        last_press_time = time.time()

        if callback is not None:
            logging.debug("running callback | thread: %s",
                            threaded_callback)
            if threaded_callback:
                thread = threading.Thread(target=callback)
                thread.daemon = True
                thread.start()
            else:
                callback()


class GpioOutputPin:
    def __init__(self, gpiochip, pin):
        self._log = logging.getLogger(self.__class__.__name__)
        self._log.debug("args gpiochip=%s pin=%d", gpiochip, pin)
        try:
            if gpiochip is None:
                self._log.error("gpiochip not found")
                raise SystemExit
            self._log.debug("type %s %s", type(gpiochip), type(pin))
            self._line = gpiochip.get_line(pin)
            self._line.request(consumer="pymedia", type=gpiod.LINE_REQ_DIR_OUT)
        except Exception as ex:
            self._log.error("Error: %s", ex)
            raise SystemExit from ex

    def set_value(self, level=0):
        """Set output."""
        if level:
            self._line.set_value(1)
        else:
            self._line.set_value(0)

    def blink(self, interval=1):
        """Blink output (blocking function)."""
        while True:
            try:
                self.set_value(0)
                time.sleep(interval)
                self.set_value(1)
                time.sleep(interval)
            except Exception as ex:
                self._log.error("Error: %s", ex)
                raise SystemExit from ex


def next_source():
    """Send (publish) a "next configuration action" for CamillaDSP."""
    REDIS.send_action('CDSP', "next_config")

def mute():
    """Send (publish) a "toggle mute action" for CamillaDSP."""
    REDIS.send_action('CDSP', "toggle_mute")


# ----------------

if __name__ == '__main__':

    REDIS = pymedia.RedisHelper('GPIOS')

    gpiochip0 = gpiod.Chip("gpiochip0")
    gpiochip1 = gpiod.Chip("gpiochip1")
    gpiochip2 = gpiod.Chip("gpiochip2")

    panel_led = GpioOutputPin(gpiochip0, 17)

    threads = pymedia.SimpleThreads()
    # rear panel led
    threads.add_target(panel_led.blink, interval=2)
    # front panel push button
    threads.add_target(wait_input_pin, gpiochip1, 23, callback=next_source)
    # rotary encoder push button
    threads.add_target(wait_input_pin, gpiochip2, 4, callback=mute)

    threads.start()

    try:
        threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
