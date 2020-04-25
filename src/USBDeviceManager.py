
import os
from glob import glob
from subprocess import check_output, CalledProcessError
from threading import Timer
import time

class USBDeviceManager:
    def __init__(self):
        def emptyFunc():
            pass
        self.refreshSignal = emptyFunc # this function is set by MainWindow

        # Set listener thread
        self.usbListenTimer = Timer(2, self.listenUSBDevices)
        self.usbListenTimer.start()

        self.lastUSBDevices = self.find_usb_devices()
    
    def listenUSBDevices(self):
        newUSBDevices = self.find_usb_devices()
        if newUSBDevices != self.lastUSBDevices:
            self.lastUSBDevices = newUSBDevices
            self.refreshSignal()

        self.usbListenTimer = Timer(2, self.listenUSBDevices)
        self.usbListenTimer.start()
        
    def find_usb_devices(self):
        sdb_devices = list(map(os.path.realpath, glob('/sys/block/sd*')))
        usb_devices = (dev for dev in sdb_devices
            if 'usb' in dev.split('/')[5])
        return dict((os.path.basename(dev), dev) for dev in usb_devices)

    def get_drive_name_size_array(self, devices=None):
        devices = devices or self.find_usb_devices()  # if devices are None: get_usb_devices
        output = check_output(['mount']).splitlines()
        output = [tmp.decode('UTF-8') for tmp in output]

        def is_usb(path):
            return any(dev in path for dev in devices)
        usb_info = (line for line in output if is_usb(line.split()[0]))
        
        usb_array = [ [info.split()[0][5:-1], info.split(" type ")[0].split("/")[-1]] for info in usb_info]

        drive_sizes = os.popen('lsblk -r | grep disk | grep sd').read().splitlines()
        drive_sizes = [[line.split()[0], line.split()[3]+'B'] for line in drive_sizes]

        drive_name_size_array = []
        for usb in usb_array:
            for size in drive_sizes:
                if usb[0] == size[0]:
                    drive_name_size_array.append(usb + [size[-1]])
        
        return drive_name_size_array

    def getUSBDevices(self):
        return self.get_drive_name_size_array()

    def setUSBRefreshSignal(self, signalfunc):
        self.refreshSignal = signalfunc