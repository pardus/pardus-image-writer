#!/usr/bin/env python3

import subprocess, sys, os, time

drive = sys.argv[1]
filepath = sys.argv[2]

# Unmount the drive before writing on it
# subprocess.call(['umount', drive+'1'])

bufferSize = 512
writtenBytes = 0
totalFileBytes = os.path.getsize(filepath)

readFile = open(filepath, "rb", buffering=0)
writeFile = open(drive, "wb", buffering=0)
try:
    oldMB = 0
    readBytes = readFile.read(bufferSize)
    while readBytes:
        writeFile.write(readBytes)
        readBytes = readFile.read(bufferSize)
        writtenBytes += bufferSize

        newMB = int(writtenBytes/1000/1000)
        if oldMB != newMB:
            oldMB = newMB
            print(f"{writtenBytes} {totalFileBytes}")
            sys.stdout.flush()
    writeFile.flush()
except IOError:
    exit(1)
else:
    readFile.close()
    writeFile.close()

time.sleep(1)
subprocess.call(['eject', drive])

exit(0)
