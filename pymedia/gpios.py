#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from time import sleep

import gpiod

import pymedia_redis
from pymedia_gpio import DigitalInputPinEvent, DigitalOutputPin
from pymedia_utils import SimpleThreads
from pymedia_cdsp import redis_cdsp_ping

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ----------------

GPIO_PULLUP = True

# ----------------

def manage_status_led(o_pin, _redis):
    """Provide visual feedback of CamillaDSP status.

    cdsp is on: led is on
    cdsp is off: led blinks

    blocking function (should be run in a thread).
    """
    while True:
        if redis_cdsp_ping(_redis):
            o_pin.set_value(1)
            sleep(10)
        else:
            for _ in range(2):
                o_pin.set_value(1)
                sleep(0.2)
                o_pin.set_value(0)
                sleep(4)


# ----------------

if __name__ == '__main__':

    _redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'GPIOS')

    gpiochip0 = gpiod.Chip("gpiochip0")
    gpiochip1 = gpiod.Chip("gpiochip1")
    gpiochip2 = gpiod.Chip("gpiochip2")

    threads = SimpleThreads()

    # rear panel led
    panel_led = DigitalOutputPin(gpiochip0, 17)
    threads.add_target(manage_status_led, panel_led, _redis)

    # front panel push button
    panel_push_btn = DigitalInputPinEvent(
            gpiochip1,
            23,
            cb_pressed=_redis.send_action,
            cb_pressed_args=("CDSP", "next_config"),
            cb_held=_redis.send_action,
            cb_held_args=("CDSP", "first_config"),
            pullup=GPIO_PULLUP,
            )
    threads.add_thread(panel_push_btn.th_wait)

    # rotary encoder push button
    encoder_push_btn = DigitalInputPinEvent(
            gpiochip2,
            4,
            cb_pressed=_redis.send_action,
            cb_pressed_args=("CDSP", "toggle_mute"),
            pullup=GPIO_PULLUP,
            )
    threads.add_thread(encoder_push_btn.th_wait)

    threads.start()

    try:
        threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
