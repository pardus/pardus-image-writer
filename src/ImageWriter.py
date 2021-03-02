#!/usr/bin/python3

import subprocess, sys, os, time, signal

stopWriting = False


def receiveSignal(number, frame):
    global stopWriting
    stopWriting = True
    return


signal.signal(signal.SIGTERM, receiveSignal)

filepath = sys.argv[1]
drive = sys.argv[2]
# Unmount the drive before writing on it
subprocess.run(['umount', "{}1".format(drive)])

bufferSize = 1024
writtenBytes = 0
totalFileBytes = os.path.getsize(filepath)

readFile = open(filepath, "rb")
writeFile = open(drive, "wb")
try:
    oldMB = 0
    readBytes = readFile.read(bufferSize)
    print("0 {}".format(totalFileBytes))
    sys.stdout.flush()
    while readBytes:
        if stopWriting == True:
            break

        writeFile.write(readBytes)
        readBytes = readFile.read(bufferSize)
        writtenBytes += bufferSize

        newMB = int(writtenBytes / 1000 / 1000 / 10)
        if oldMB != newMB:
            oldMB = newMB
            print("{} {}".format(writtenBytes, totalFileBytes))
            os.fsync(writeFile)
            sys.stdout.flush()
    writeFile.flush()
except IOError:
    exit(1)
else:
    os.fsync(writeFile)
    readFile.close()
    writeFile.close()

print("{} {}".format(totalFileBytes, totalFileBytes))
time.sleep(1)
subprocess.call(['eject', drive])

exit(0)
