#!/usr/bin/env python3

import subprocess, sys, os, time

drive = sys.argv[1]
filepath = sys.argv[2]

# Unmount the drive before writing on it
subprocess.call(['umount', f"{drive}1"])

bufferSize = 1024
writtenBytes = 0
totalFileBytes = os.path.getsize(filepath)

readFile = open(filepath, "rb")
writeFile = open(drive, "wb")
try:
    oldMB = 0
    readBytes = readFile.read(bufferSize)
    print(f"0 {totalFileBytes}")
    sys.stdout.flush()
    while readBytes:
        writeFile.write(readBytes)
        readBytes = readFile.read(bufferSize)
        writtenBytes += bufferSize

        newMB = int(writtenBytes/1000/1000/10)
        if oldMB != newMB:
            oldMB = newMB
            print(f"{writtenBytes} {totalFileBytes}")
            os.fsync(writeFile)
            sys.stdout.flush()
    writeFile.flush()
except IOError:
    exit(1)
else:
    os.fsync(writeFile)
    readFile.close()
    writeFile.close()

print(f"{totalFileBytes} {totalFileBytes}")

exit(0)
