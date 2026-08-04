#!/usr/bin/python3

import os
import signal
import subprocess
import sys
import time
from USBDeviceManager import USBDeviceManager

stopWriting = False


def receiveSignal(number, frame):
    global stopWriting
    stopWriting = True
    return


signal.signal(signal.SIGTERM, receiveSignal)

if len(sys.argv) != 3:
    print("Usage: ./ImageWrite.py /file/path/iso.iso /dev/sda")
    exit(1)

filepath = sys.argv[1]
drive = sys.argv[2]

# Find if the drive is a USB device
device_manager = USBDeviceManager()
devices = device_manager.get_usb_devices()


def find_drive_in_devices(drive, devices):
    for [device, label, size] in devices:
        print(device, "==", drive)
        if drive == f"/dev/{device}":
            return True

    return False


if not find_drive_in_devices(drive, devices):
    print("The device is not a USB removable drive.")
    exit(1)

# Unmount the drive before writing on it
subprocess.run(["umount", "{}1".format(drive)])

bufferSize = 4096
writtenBytes = 0
totalFileBytes = os.path.getsize(filepath)

readFile = open(filepath, "rb")
writeFile = open(drive, "wb")
try:
    i = 0
    oldMB = 0
    readBytes = readFile.read(bufferSize)
    print("0 {}".format(totalFileBytes))
    sys.stdout.flush()
    while readBytes:
        i += 1
        if stopWriting:
            sys.stderr.write("---Writing stopped---\n")
            break

        writeFile.write(readBytes)
        readBytes = readFile.read(bufferSize)
        writtenBytes += bufferSize

        newMB = int(writtenBytes / 1000 / 1000 / 10)
        if oldMB != newMB:  # print on every 10MB
            oldMB = newMB
            print("{} {}".format(writtenBytes, totalFileBytes))
            sys.stdout.flush()

        if i % 5000 == 0:  # sync regularly
            os.fdatasync(writeFile)

    if not stopWriting:
        writeFile.flush()
except IOError:
    exit(1)
else:
    if not stopWriting:
        os.fsync(writeFile)
    readFile.close()
    writeFile.close()

print("{} {}".format(totalFileBytes, totalFileBytes))
time.sleep(1)
subprocess.call(["eject", drive])

exit(0)
