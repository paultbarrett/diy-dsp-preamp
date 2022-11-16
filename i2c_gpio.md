# I2C/GPIO setup

([Rockpi-S headers pinout and pin 
addressing](https://wiki.radxa.com/RockpiS/hardware/gpio))

## GPIO - chardev (with libgpiod):

```
apt install python3-libgpiod gpiod
gpiodetect
gpioinfo gpiochip0
```

permissions: `/etc/udev/rules.d/99-gpiochip.rules`

## I2C

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

### libmraa (not mandatory)

Add radxa apt sources to `/etc/apt/sources.list.d/apt-radxa-com.list`:

```
deb http://apt.radxa.com/buster-stable/ buster main
deb http://apt.radxa.com/buster-testing/ buster main
```

Import key with `wget -O -  apt.radxa.com/buster-testing/public.key | sudo apt-key add -`

Update/upgrade: `apt update ; apt upgrade`

Install libraa: `apt install libmraa-rockpis`

Tests:

- `mraa-gpio get 12`
- `mraa-i2c detect 0` (i2c-0 overlay should be enabled !).


### I2C Peripherals

Add user to group i2c.

Adafruit / 5.x armbian: `pip3 install adafruit-extended-bus`

- ssd1306 OLED display: `pip3 install adafruit-circuitpython-ssd1306`
  [adafruit repo](https://github.com/adafruit/Adafruit_CircuitPython_SSD1306)

- DPS310 barometer: `pip3 install adafruit-circuitpython-dps310`
  [adafruit repo](https://github.com/adafruit/Adafruit_CircuitPython_DPS310)

## monitoring

I use snmpd's `extend` feature to run the python script and return the values
for use in Zabbix. This is probably much lighter than installing zabbix-agent
and using a custom userParameter entry.

eg. snmpd.conf: `extend  weather /path/to/the/python/script`

this can then be accessed at oid
`NET-SNMP-EXTEND-MIB::nsExtendOutputFull."weather"`, eg. with `snmpget -v2c -c
community -On rockpi-s 'NET-SNMP-EXTEND-MIB::nsExtendOutputFull."weather"'`

notes:

- fix permissions according to your setup. Eg. instead of adding the snmpd user
  to the i2c group, I'm running the script with sudo and a properly configured
  sudoers.d entry.
- add locking to prevent concurrent use - eg. if concurrent snmp queries are
  sent. (on my setup I also store the values to a temp file and read them from
  there if they're not older than x seconds ; I can upload the script it if
  someone is interested).

zabbix: see the exported xml template; it's using a snmpv2 type (snmpv1 would
work too) using the oid above and two dependent items for pressure/temperature,
parsing the main item with a regex (eg.  `(^| )temp:(-?[0-9\.]+)( |$)`).

## long distance wire

https://www.nxp.com/docs/en/application-note/AN11075.pdf

->

- pair 1: gnd
- pair 2: vcc
- pair 3: vcc/SDA
- pair 4: gnd/SDL


## Old / deprecated

Adafruit / 4.x armbian:

As root: `apt install python3-dev python3-pip`

As user:

```
pip3 install --upgrade setuptools
pip3 install wheel
pip3 install adafruit-circuitpython-dps310
```


