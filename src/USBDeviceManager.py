#!/usr/bin/python3

import os
from glob import glob
from pyudev import Context, Monitor, Devices
from pyudev import MonitorObserver, DeviceNotFoundAtPathError


class USBDeviceManager:
    def __init__(self):
        self.refreshSignal = lambda a: a  # this function is set by MainWindow
        self.context = Context()
        self.monitor = Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem="block", device_type="disk")

        def log_event(action, device):
            self.refreshSignal()

        self.observer = MonitorObserver(self.monitor, log_event)
        self.observer.start()

    def _find_usb_devices(self):
        sdb_devices = list(map(os.path.realpath, glob("/sys/block/sd*")))
        usb_devices = []
        for dev in sdb_devices:
            for prop in dev.split("/"):
                if "usb" in prop:
                    usb_devices.append(os.path.basename(dev))

        return usb_devices

    def get_usb_devices(self):
        deviceList = []
        usb_devices = self._find_usb_devices()
        for blockName in usb_devices:
            try:
                device = Devices.from_path(
                    self.context, "/sys/block/{}".format(blockName)
                )
                deviceInfo = []
                # 'sda'
                deviceInfo.append(blockName)

                # 'FEDAR32'
                deviceLabel = device.get("ID_FS_LABEL", "")
                deviceVendor = device.get("ID_VENDOR", "")
                deviceModel = device.get("ID_MODEL", "NO_MODEL")
                if deviceLabel == "":
                    deviceInfo.append("{} {}".format(deviceVendor, deviceModel))
                else:
                    deviceInfo.append(deviceLabel)

                # '4GB'
                blockCount = int(
                    open("/sys/block/{}/size".format(blockName)).readline()
                )
                blockSize = int(
                    open(
                        "/sys/block/{}/queue/logical_block_size".format(blockName)
                    ).readline()
                )

                size = blockCount * blockSize
                if size >= 1000000000000:
                    size = "%.0fTB" % round(size / 1000000000000)
                elif size >= 1000000000:
                    size = "%.0fGB" % round(size / 1000000000)
                elif size >= 1000000:
                    size = "%.0fMB" % round(size / 1000000)
                elif size >= 1000:
                    size = "%.0fkB" % round(size / 1000)
                else:
                    size = "%.0fB" % round(size)
                deviceInfo.append("{}".format(size))

                # Add device to list
                if blockCount > 0:
                    deviceList.append(deviceInfo)
            except DeviceNotFoundAtPathError:
                print(f"Device {blockName} not found")

        return deviceList

    def connect_usb_refresh_signal(self, signalfunc):
        self.refreshSignal = signalfunc
