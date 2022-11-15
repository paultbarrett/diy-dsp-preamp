# Bluetooth A2DP sink

Overview:
- (once:) manually pair the BT device with `bluetoothctl`
- wireplumber sets up the A2DP sink automatically when the BT device is detected
- a python user script monitoring dbus bluez events starts/stops stuff (eg.
  squeezelite) when the BT device is connected/disconnected

## BT dongle firmware

UB500 firmware, if dmesg shows
`hci0: RTL: firmware file rtl_bt/rtl8761bu_fw.bin not found`:

```
cd /tmp
wget
http://ftp.us.debian.org/debian/pool/non-free/f/firmware-nonfree/firmware-realtek_20210818-1_all.deb
dpkg -i firmware-realtek_20210818-1_all.deb
```

## bluez

`apt install bluez bluez-tools`

[doc](https://www.makeuseof.com/manage-bluetooth-linux-with-bluetoothctl/)

```
bluetoothctl scan on
bluetoothctl pair 98:8E:79:00:5A:D3     # that's the Qudelix 5K
bluetoothctl connect 98:8E:79:00:5A:D3
bluetoothctl trust 98:8E:79:00:5A:D3    # needed ?
bluetoothctl discoverable on            # test
bluetoothctl pairable on                # test
bluetoothctl paired-devices
```

Note:
- a running agent *is* needed
- sometimes a reboot will fix BT connection errors
- use `btmon` to debug
- 5K: pairing is obviously done in Qudelix pairing mode, but it seems that the first time 'connect' should also happen when in pairing mode ?
- see https://forum.qudelix.com/post/having-trouble-getting-multipoint-pairing-between-my-ipad-pro-and-my-iphone-12-max-12380165


# pipewire + wireplumber for BT devices

[install](pipewire_debian_testing.md) more recent versions of pipewire and
wireplumber.

```
apt -t testing install libldacbt-abr2 libspa-0.2-bluetooth pipewire-audio-client-libraries python3-pydbus
useradd -m pwbt
usermod -G audio pwbt
loginctl enable-linger pwbt
```

system files:

```
/etc/systemd/system/bt-agent.service
```

`monitor_bt.py` (started from `monitor-bt.service`) monitors the presence of the
BT sink and starts/stops the `bt-presence.target` accordingly. The target pulls
for instance squeezelite and an alsa loopback (with `arecord|aplay`) to play
content from jacktrip (if any).

relevant user files:

```
/home/pwbt/bin/monitor_bt.py	# requires python3-pydbus
/home/pwbt/.config/systemd/user/monitor-bt.service
/home/pwbt/.config/systemd/user/bt-presence.target
# the services below are part of bt-presence.target:
/home/pwbt/.config/systemd/user/squeezelite.service
/home/pwbt/.config/systemd/user/alsa-loop-loopback1.service
```

Enable systemd user stuff:

```
systemctl --user enable monitor-bt.service
systemctl --user enable squeezelite.service
systemctl --user enable alsa-loop-loopback1.service
```

user files to properly configure pipewire/wireplumber:

```
/home/pwbt/.config/wireplumber/bluetooth.lua.d/80-disable-logind.lua
/home/pwbt/.config/wireplumber/bluetooth.lua.d/80-ldac-hq.lua
/home/pwbt/.config/wireplumber/main.lua.d/80-disable-alsa-monitor.lua
/home/pwbt/.config/wireplumber/main.lua.d/90-enable-all.lua
```

Main pipewire/wireplumber tweaks:

- misc fixes because we're headless, no RT, ...
- no alsa monitor/dynamic creation (players should play only to the A2DP sink)

Misc. notes:

- the BT agent could be started by the `monitor_bt.py` script.
- the `arecord|aplay` loopback started by `alsa-loop-loopback1.service` could
  probably be replaced by a pipewire loopback but no luck trying to make it
  work.


# misc

temp debug sound directly on BT device (eg. qudelix)

```
/usr/local/bin/squeezelite \
    -o hw:CARD=Q441KHz,DEV=0 \
    -n "rockpi-s-Qudelix-5K_USB_DAC_44" \
    -m "e4:e1:7e:80:f3:03"
```
