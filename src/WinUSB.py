#!/usr/bin/python3

import subprocess, sys, os, time, stat, signal
import time

def run(cmd,vital=True):
    print(cmd)
    subprocess.run(cmd,check=vital)
    os.system("sync")

class IsoCopy:
    def errMsg(self, msg=""):
        sys.stderr.write("\x1b[31;1mError: \x1b[;0m{}".format(msg))
        exit(8)

    def __init__(self, iso_path, drive):
        # Define variables with fallback
        self.isoTmpFolder = "/run/pardus-iso-tmp/"
        self.usbMountFolder = "/run/pardus-usb-tmp/"
        self.isoPath = iso_path
        self.drive = drive
        self.isoName = ""

        # SIGTERM signal
        signal.signal(signal.SIGTERM, self.receiveSignal)

        # Check variables
        if not os.path.isfile(iso_path):
            self.errMsg("ISO file not found")
        if not stat.S_ISBLK(os.stat(drive).st_mode):
            self.errMsg("{} is not a valid block device".format(drive))


    def receiveSignal(self, number, frame):
        run(["sync"])
        exit(15)

    def get_size(self,disk):
        return int(subprocess.getoutput("fdisk -l | grep Disk | grep "+disk+" | cut -f \"5\" -d \" \" | head -n 1"))

    def run(self):
        self.formatDrive()

        self.mountFolders()
        self.copyFiles()
        self.installGrub()

        self.windowsISOAddition()

        self.finishEvent()

    def formatDrive(self):
        # Unmount the drive before writing on it
        run(["sh", "-c", ("ls {}* | xargs umount -lf ".format(self.drive))],vital=False)

        # Format USB to FAT32
        run(["dd", "if=/dev/zero", "of={}".format(self.drive), "bs=512", "count=1", "oflag=sync"])
        run(["parted", self.drive, "mktable", "msdos"])
        size=(self.get_size(self.drive)/1000**2)
        print(size)
        run(["parted", self.drive, "mkpart", "primary", "ntfs", "1", "{}M".format((size-1))])
        run(["bash", "-c", "yes | parted "+ self.drive+ " ---pretend-input-tty mkpart primary fat32 2 100%"]) 
        run(["wipefs", "-a", (self.drive + "1"), "--force"])
        run(["wipefs", "-a", (self.drive + "2"), "--force"])
        run(["mkfs.fat", "-F32", (self.drive + "2")])
        run(["mkfs.ntfs", "-f", "-v", (self.drive + "1")])
        run(["parted", self.drive, "set", "1", "boot", "on"])
        run(["sync"])
        time.sleep(3)

    def mountFolders(self):
        # Unmount first if already mounted
        run(["umount", self.isoTmpFolder],vital=False)
        run(["umount", self.usbMountFolder],vital=False)
        run(["umount", (self.drive + "1")],vital=False)

        run(["mkdir", self.isoTmpFolder],vital=False)
        run(["mount", "-o", "ro", "-t", "auto", self.isoPath, self.isoTmpFolder])

        run(["mkdir", self.usbMountFolder])
        if not os.path.exists(os.path.dirname(os.path.abspath(__file__))+"/../uefi-ntfs.img"):
            run(["wget","-c","https://github.com/pbatard/rufus/raw/master/res/uefi/uefi-ntfs.img","-O",os.path.dirname(os.path.abspath(__file__))+"/../uefi-ntfs.img"])
        run(["dd","if="+os.path.dirname(os.path.abspath(__file__))+"/../uefi-ntfs.img","of={}2".format(self.drive)])
        run(["sync"])
        run(["parted", self.drive, "set", "2", "hidden", "on"])
        run(["parted", self.drive, "set", "2", "esp", "on"])
        run(["mount", (self.drive + "1"), self.usbMountFolder])

    def copyFiles(self):
        folders = os.listdir(self.isoTmpFolder)
        fileCount = len(folders)
        i = 0
        for file in folders:
            run(["rsync", "--archive", "--no-links", "--quiet", "--no-D", "--acls",
                            self.isoTmpFolder + file, self.usbMountFolder])

            run(["sync"])
            print("PROGRESS:{}:{}".format(i, fileCount))
            sys.stdout.flush()
            i += 1

    def installGrub(self):
        # Install GRUB
        run(["grub-install", "--target=i386-pc", "--force", "--removable",
            "--boot-directory=/{}/boot".format(self.usbMountFolder),
            "--locales=", self.drive])
        run(["sync"])

    def windowsISOAddition(self):
        with open(self.usbMountFolder + "/boot/grub/grub.cfg", "a") as grubcfg:
            grubcfg.write("insmod part_msdos\n")
            grubcfg.write("insmod ntfs\n")
            grubcfg.write("insmod ntldr\n")
            grubcfg.write("ntldr /bootmgr\n")
            grubcfg.write("boot\n")

    def finishEvent(self):
        # Unmount the temp folder
        run(["umount", self.isoTmpFolder])
        run(["umount", (self.drive + "1")])
        run(["rm", "-rf", self.isoTmpFolder])
        run(["rm", "-rf", self.usbMountFolder])


if __name__ == "__main__":
    # Iso write action
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: {} [iso path] [drive]\n".format(sys.argv[0]))
        exit(1)
    i = IsoCopy(sys.argv[1], sys.argv[2])
    i.run()
