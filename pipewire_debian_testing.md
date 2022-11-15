# install a recent pipewire on debian

```
echo 'APT::Default-Release "stable";' | sudo tee /etc/apt/apt.conf.d/99defaultrelease
echo "deb http://ftp.de.debian.org/debian/ testing main contrib non-free" | sudo tee /etc/apt/sources.list.d/testing.list
sudo apt update
sudo apt -t testing install pipewire wireplumber
```

on a headless setup:

wireplumber:
- comment `default_access.enable()` in `main.lua.d/90-enable-all.lua`

also, to avoid pipewire/wireplumber from starting when ssh'in as user `user`:

```
systemctl --user disable pipewire.socket
systemctl --user disable wireplumber
systemctl --user mask pipewire
systemctl --user mask pipewire.socket
systemctl --user mask wireplumber
```
