#!/usr/bin/python3

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from time import sleep

import gpiod

import pymedia_redis
import pymedia_gpio
import pymedia_utils
from pymedia_cdsp import redis_cdsp_ping

from pymedia_const import REDIS_SERVER, REDIS_PORT, REDIS_DB

# ----------------

def next_source(_redis):
    """Send (publish) a "next configuration action" for CamillaDSP."""
    _redis.send_action('CDSP', "next_config")

def mute(_redis):
    """Send (publish) a "toggle mute action" for CamillaDSP."""
    _redis.send_action('CDSP', "toggle_mute")

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

    redis = pymedia_redis.RedisHelper(REDIS_SERVER, REDIS_PORT, REDIS_DB,
                                      'GPIOS')

    gpiochip0 = gpiod.Chip("gpiochip0")
    gpiochip1 = gpiod.Chip("gpiochip1")
    gpiochip2 = gpiod.Chip("gpiochip2")

    panel_led = pymedia_gpio.GpioOutputPin(gpiochip0, 17)

    threads = pymedia_utils.SimpleThreads()

    # rear panel led
    threads.add_target(manage_status_led, panel_led, redis)

    # front panel push button
    threads.add_target(pymedia_gpio.wait_input_pin, gpiochip1, 23,
                       callback=next_source, cb_args=(redis,))

    # rotary encoder push button
    threads.add_target(pymedia_gpio.wait_input_pin, gpiochip2, 4, callback=mute,
                       cb_args=(redis,))

    threads.start()

    try:
        threads.join()
    except KeyboardInterrupt:
        print("Received KeyboardInterrupt, shutting down...")
