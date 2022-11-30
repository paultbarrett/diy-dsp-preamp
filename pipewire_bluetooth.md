# Bluetooth receiver and streamer

Receiver overview:

- BT controller is always pairable and discoverable
- BT sources are played to `Loopback2`

Streamer overview:

- (once:) manually pair the BT device with `bluetoothctl`
- wireplumber sets up the A2DP sink automatically when the BT device is detected
- a python user script monitoring dbus bluez events starts/stops stuff (eg.
  squeezelite) when the BT device is connected/disconnected

## Installation

### BT dongle firmware:

UB500 firmware, if dmesg shows
`hci0: RTL: firmware file rtl_bt/rtl8761bu_fw.bin not found`:

```
cd /tmp
wget
http://ftp.us.debian.org/debian/pool/non-free/f/firmware-nonfree/firmware-realtek_20210818-1_all.deb
dpkg -i firmware-realtek_20210818-1_all.deb
```

### Bluez and pipewire

bluez: `apt install bluez bluez-tools`

[install](pipewire_debian_testing.md) more recent versions of pipewire and
wireplumber.

```
apt -t testing install libldacbt-abr2 libspa-0.2-bluetooth \
    pipewire-audio-client-libraries python3-pydbus
useradd -m pwbt
usermod -G audio pwbt
loginctl enable-linger pwbt
```

### BT Streamer / pairing

[doc](https://www.makeuseof.com/manage-bluetooth-linux-with-bluetoothctl/)

Done once:

```
bluetoothctl scan on
bluetoothctl pair 98:8E:79:00:5A:D3     # that's the Qudelix 5K
bluetoothctl connect 98:8E:79:00:5A:D3
bluetoothctl trust 98:8E:79:00:5A:D3    # needed ?
bluetoothctl discoverable on            # test
bluetoothctl pairable on                # test
bluetoothctl paired-devices
```

and add a line to `/home/pwbt/bt_sinks.def` like so:

```
/org/bluez/hci0/dev_98_8E_79_00_5A_D3
```

Note:

- a running agent *is* needed when trying to pair the BT device with the
  controller
- sometimes a reboot will fix BT connection errors
- use `btmon` to debug
- 5K: pairing is obviously done in Qudelix pairing mode, but it seems that the
  first time 'connect' should also happen when in pairing mode ?
- multipoint pairing: see [this forum
  post](https://forum.qudelix.com/post/having-trouble-getting-multipoint-pairing-between-my-ipad-pro-and-my-iphone-12-max-12380165)


### BT Receiver / pairing

Configure the BlueZ daemon to allow re-pairing without user interaction:

```
$ sudo sed -i 's/#JustWorksRepairing.*/JustWorksRepairing = always/' /etc/bluetooth/main.conf
```

Also see `speaker-agent.py` below.


### Pipewire (streamer and receiver)

`speaker-agent.py`: used both as agent and to allow audio BT devices for the
receiver. Download
[here](https://github.com/fdanis-oss/pw_wp_bluetooth_rpi_speaker)

`monitor_bt.py` (started from `monitor-bt.service`): monitors the presence of
the BT sink and starts/stops the `bt-presence.target` accordingly. The target
pulls for instance squeezelite and an alsa loopback (with `arecord|aplay`) to
play content from jacktrip (if any).
Known BT sinks should be listed in `/home/pwbt/bt_sinks.def` like so:

```
/org/bluez/hci0/dev_98_8E_79_00_5A_D3
[...]
```

note: `speaker-agent.py` and `monitor_bt.py` could be merged in a single program
(no time to do that - one uses python-dbus, the other python-pydbus).


relevant user files:

```
/home/pwbt/bin/monitor_bt.py
/home/pwbt/bin/speaker-agent.py
/home/pwbt/.config/systemd/user/monitor-bt.service
/home/pwbt/.config/systemd/user/bt-presence.target
# the services below are part of bt-presence.target:
/home/pwbt/.config/systemd/user/squeezelite.service
/home/pwbt/.config/systemd/user/alsa-loop-loopback1.service
```

Enable systemd service (as user):

```
systemctl --user enable monitor-bt.service
systemctl --user enable bt-agent.service
systemctl --user enable squeezelite.service
systemctl --user enable alsa-loop-loopback1.service
```

user files to properly configure pipewire/wireplumber:

```
.config/pipewire/pipewire.conf
.config/wireplumber/bluetooth.lua.d/80-disable-logind.lua
.config/wireplumber/bluetooth.lua.d/80-ldac-hq.lua
.config/wireplumber/bluetooth.lua.d/80-route_sources_to_alsa.lua
.config/wireplumber/main.lua.d/80-disable-alsa-monitor.lua
.config/wireplumber/main.lua.d/80-no_persistence.lua
.config/wireplumber/main.lua.d/90-enable-all.lua
.config/wireplumber/policy.lua.d/80-no_persistence.lua
```

Main pipewire/wireplumber tweaks:

- misc fixes because we're headless, no RT, ...
- no alsa monitor/dynamic creation (players should play only to BT A2DP sinks)
- BT sources are routed to `Loopback2`. Apps play to recent BT sinks by default
  (TODO - force it with a wireplumber rule)

Misc. notes:

- the `arecord|aplay` loopback started by `alsa-loop-loopback1.service` could
  be replaced by a pipewire loopback but no luck trying to make it work.


# misc

temp debug sound directly on BT device (eg. qudelix)

```
/usr/local/bin/squeezelite \
    -o hw:CARD=Q441KHz,DEV=0 \
    -n "rockpi-s-Qudelix-5K_USB_DAC_44" \
    -m "e4:e1:7e:80:f3:03"
```
