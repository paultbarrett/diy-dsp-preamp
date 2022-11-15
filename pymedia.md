# "pymedia" python programs

Those are a collection of programs with redis as IPC. Overview (look at comments
in the code for more info):

- `cdsp.py`: (loop) connect to a running CamillaDSP instance, listen to/process
  volume change, mute, config change, events, etc., send events on
  disconnect/reconnect, update RMS/peak signal values, ...

- `display.py`: updates/blanks the display, listening for redis messages from
  other programs (also updating at regular intervals). Shows player status,
  config index (A, B, ...), RMS/peak signal level, main volume, and mute status.

  ![img/display.jpg]

- `gpios.py`: blinks a rear panel led, wait for mute and source buttons events
  (interrupt based with libgpiod - so no polling), and send redis
  events/messages accordingly.

- `lfe_tone.py`: plays an inaudible low frequency tone to wake-up a subwoofer in
  standby(/eco) mode (or to prevent the sub from entering standby), listening
  for redis messages from other other programs (also playing at regular
  intervals). Note - the tone is played depending on mute/player status/... so
  it won't keep the sub powered on if nothing is being played

- `lms.py`: listen to events to play/pause/turn on-off/... a LMS player like
  squeezelite, and sends events when a player change has occured.

- `rotary_encoder.py`: send volume change events to CamillaDSP. Interrupt-based
  (no polling), uses a [state machine](https://github.com/buxtronix/arduino/tree/master/libraries/Rotary)
  for proper processing/debouncing, and buffers/reprocess volume events that are
  too close to avoid sending too many volume changes to CamillaDSP


Q/Why not a single program: it's much easier to have several pieces of
functionality running independently (a good example is postfix), one can
stop/restart only one program without interrupting the others, etc.

Q/Why Redis: because it's uber simple, "plug-and-play" and in that case has no
impact on performance (really - I've measured various tasks' completion times
and couldn't notice any different between using a single large program blob
without redis and standalone python programs communicating through redis). I
looked at dbus but it's on another level of complexity - even trying to choose
the proper python lib was difficult (the official implementation isn't
recommended, one implementation works well but isn't maintained, other
implementations have taken over but aren't feature-complete, etc.).

Q/Why use threads rather than asyncio: well, I actually implemented almost
everything with asyncio until I got really annoyed by the few blocking functions
here and there and issues with catching exceptions (I'm not a really good python
programer BTW). So in the end, instead of mixing asyncio, executors and
threads, I refactored everything to use threads. It ended up being much simpler.


## Installation

### I2C / GPIO

Follow [those instructions](i2c_gpio.md).

Add permissions to `io` user:

```
useradd -m -G gpio,i2c io	# or usermod -aG gpio,i2c io
```


### Redis

```
apt install redis python3-redis
systemctl enable redis-server
```

`/etc/redis/redis.conf` tweaks:
- don't save state (to avoid SD writes): `save ""`
- max mem: `maxmemory 20000000`

`/var/log` is tmpfs mounted in my case, so `/var/log/redis` needs to be created
as startup:

`/etc/tmpfiles.d/redis.conf`:

```
d       /var/log/redis  0700    redis   redis - -
```

### LMSQuery (for lms.py)

`apt intall python3-requests`

[cli doc](https://github.com/elParaguayo/LMS-CLI-Documentation/blob/master/LMS-CLI.md)

### pycamilladsp (for cdsp.py)

as user:

```
pip3 install git+https://github.com/HEnquist/pycamilladsp.git
```

## Starting scripts

See:

```
/etc/default/pymedia
/etc/systemd/pymedia@.service
/etc/systemd/pymedia.target
```

Commands:

```
systemctl enable pymedia.target
systemctl enable pymedia@gpios
systemctl enable pymedia@lms
systemctl enable pymedia@display
systemctl enable pymedia@cdsp
systemctl enable pymedia@rotary_encoder
systemctl enable pymedia@lfe_tone
```

Q/Why use systemd user services (eg. pipewire/jacktrip) and systemd system
service here (especially when they're run as user 'io'): I tried, but camilladsp
is started by udev as a service template so we'd have to start camilladsp
together with the "pymedia" programs ; that could be done with a target but 1/
pymedia programs aren't necessarily bound to a sound interface (eg. the display
is device agnostic) and 2/ pymedia stuff require redis to run before being
started and systemd user services can't "Require:" system services. So we'd
have to come up with a way to wait for redis ; it's not hard - a simple query
loop and we'd be good. But - again - while all of this is feasible, it was much
easier to do it with system services.

