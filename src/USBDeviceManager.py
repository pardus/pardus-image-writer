import os
from glob import glob
from pyudev import Context, Monitor, Devices
from pyudev import MonitorObserver


class USBDeviceManager:
    def __init__(self):
        self.refreshSignal = (lambda a: a)  # this function is set by MainWindow
        self.context = Context()
        self.monitor = Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem="block", device_type="disk")

        def log_event(action, device):
            self.refreshSignal()

        self.observer = MonitorObserver(self.monitor, log_event)
        self.observer.start()

    def find_usb_devices(self):
        sdb_devices = list(map(os.path.realpath, glob('/sys/block/sd*')))
        usb_devices = []
        for dev in sdb_devices:
            for prop in dev.split('/'):
                if 'usb' in prop:
                    usb_devices.append(os.path.basename(dev))

        return usb_devices

    def get_device_infos(self):
        deviceList = []
        usb_devices = self.find_usb_devices()
        for blockName in usb_devices:
            try:
                device = Devices.from_path(self.context, "/sys/block/{}".format(blockName))
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
                blockCount = int(open("/sys/block/{}/size".format(blockName)).readline())
                blockSize = int(open("/sys/block/{}/queue/logical_block_size".format(blockName)).readline())
                deviceInfo.append("{}GB".format(int((blockCount * blockSize) / 1000 / 1000 / 1000)))

                # Add device to list
                if blockCount > 0:
                    deviceList.append(deviceInfo)
            except:
                pass

        return deviceList

    def getUSBDevices(self):
        return self.get_device_infos()

    def setUSBRefreshSignal(self, signalfunc):
        self.refreshSignal = signalfunc
