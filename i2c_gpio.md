# I2C/GPIO setup


## GPIO - chardev (with libgpiod):

(Instructions tested on the rockpi-S and rpi3)

```
apt install python3-libgpiod gpiod
gpiodetect
gpioinfo gpiochip0
```

Make sure that your user is the `gpio` group - if not:

```
usermod -aG gpio username
```

Also make sure that `/dev/gpiochip*` is owned by group `gpio` like so:

```
crw-rw---- 1 root gpio 254, 0 Nov 15 20:20 /dev/gpiochip0
crw-rw---- 1 root gpio 254, 1 Nov 15 20:20 /dev/gpiochip1
[...]
```

If not you'd have to add the proper udev permissions; see
`/etc/udev/rules.d/99-gpiochip.rules`


## I2C

### Rockpi-S setup

I2C/SPI/UART/... need to be enabled via overlays:

- [doc](https://docs.armbian.com/User-Guide_Allwinner_overlays/) (despite being
  for allwinner, also applies to rockchip)
- available overlays are listed [here](https://wiki.radxa.com/Device-tree-overlays)
  and in `/boot/dtb/rockchip/overlay/README.rockchip-overlays`

eg. `overlays=i2c0 i2c1` to enable both i2c0 and i2c1; a `/dev/i2c-X` entry
should now exist.

Note: the serial console uses i2c0 pins ; if i2c0 is needed:
- set `console=` in armbianEnv.txt
- recompile `boot.scr` with `mkimage -C none -A arm -T script -d /boot/boot.cmd /boot/boot.scr`
- `systemctl mask serial-getty@ttyS0.service`
- reboot

### i2c-tools

`apt install i2c-tools`

`i2c-detect 0` (note: seems to detect a bunch of random stuff when no device is connected compared to `mraa-i2c detect 0`)


### I2C Peripherals

Add user to group i2c:

```
usermod -aG i2c username
```

Adafruit / 5.x armbian: `pip3 install adafruit-extended-bus`

- ssd1306 OLED display: `pip3 install adafruit-circuitpython-ssd1306`
  [adafruit repo](https://github.com/adafruit/Adafruit_CircuitPython_SSD1306)

- DPS310 barometer: `pip3 install adafruit-circuitpython-dps310`
  [adafruit repo](https://github.com/adafruit/Adafruit_CircuitPython_DPS310)


## Header pinout

- [Rockpi-S headers pinout and pin 
addressing](https://wiki.radxa.com/RockpiS/hardware/gpio)

- [rpi3](https://pinout.xyz/)
