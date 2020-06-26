
import os
from glob import glob
from pyudev import Context, Monitor, Devices
from pyudev import MonitorObserver

class USBDeviceManager:
    def __init__(self):
        self.refreshSignal = (lambda a: a) # this function is set by MainWindow
        self.context = Context()
        self.monitor = Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem="block", device_type="partition")

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
            device = Devices.from_name(self.context, 'block', f"{blockName}1")
            deviceInfo = []
            # 'sda'
            deviceInfo.append(blockName)

            # 'FEDAR32'
            deviceInfo.append(device.get('ID_FS_LABEL', 'NO_LABEL'))

            # '4GB'
            blockCount = int(open(f"/sys/block/{blockName}/size").readline())
            blockSize = int(open(f"/sys/block/{blockName}/queue/logical_block_size").readline())
            deviceInfo.append(f"{int((blockCount*blockSize)/1000/1000/1000)}GB")

            # Add device to list
            deviceList.append(deviceInfo)
        return deviceList

    def getUSBDevices(self):
        return self.get_device_infos()

    def setUSBRefreshSignal(self, signalfunc):
        self.refreshSignal = signalfunc
