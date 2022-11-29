#!/usr/bin/python3

# https://raspberrypi.stackexchange.com/questions/96493/rpi-zero-w-how-to-automatically-accept-bluetooth-pairing-and-log-mac-and-info
import pydbus
import subprocess
import sys
import re
from gi.repository import GLib

bus = pydbus.SystemBus()
mng = bus.get('org.bluez', '/')

class DeviceMonitor:
    def __init__(self, path_obj):
        self.device = bus.get('org.bluez', path_obj)
        self.device.onPropertiesChanged = self.prop_changed
        print(f'Device added to monitor {self.device.Address}')

    def prop_changed(self, iface, props_changed, props_removed):
        """Event handler for a device property change"""
        con_status = props_changed.get('Connected', None)
        if con_status is not None:
            if con_status:
                print(f'Connected {self.device.Address}')
                process = subprocess.run(['systemctl', '--user', 'start', 'bt-presence.target'])
            else:
                print(f'Disconnected {self.device.Address}')
                process = subprocess.run(['systemctl', '--user', 'stop', 'bt-presence.target'])

def new_iface(path, iface_props):
    """Check to see if a new device has been added"""
    print('Interface Added')
    device_addr = iface_props.get('org.bluez.Device1', {}).get('Address')
    if device_addr:
        DeviceMonitor(path)

mng.onInterfacesAdded = new_iface

# Get all the known devices and add them to DeviceMonitor
#mng_objs = mng.GetManagedObjects()
#for path in mng_objs:
#    dev_props = mng_objs[path].get('org.bluez.Device1', {})
#    if dev_props:
#        DeviceMonitor(path)

# Load known devices from conf file and add them to DeviceMonitor
regex = re.compile("^/org.*")
with open(sys.argv[1], 'r') as conf_file:
    for line in conf_file:
        if regex.search(line):
            DeviceMonitor(line.strip())


# Start the eventloop to monitor BlueZ events
mainloop = GLib.MainLoop()
try:
    mainloop.run()
except KeyboardInterrupt:
    mainloop.quit()


