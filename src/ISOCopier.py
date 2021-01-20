#!/usr/bin/python3

import subprocess, sys, os, time, stat, signal

class IsoCopy:
    def errMsg(self,msg=""):
        sys.stderr.write("\x1b[31;1mError: \x1b[;0m{}".format(msg))
        exit(8)

    def __init__(self,iso_path,drive):
        # Define variables with fallback
        self.isoTmpFolder = "/tmp/pardus-iso-tmp/"
        self.usbMountFolder = "/tmp/pardus-usb-tmp/"
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
        subprocess.run(["sync"])
        exit(15)

    def run(self):
        self.readIsoName()
        self.formatDrive()

        self.mountFolders()
        self.copyFiles()
        self.installGrub()
        
        if "windows" in self.isoName.lower():
            self.windowsISOAddition()

        self.finishEvent()

    def readIsoName(self):
        with open(self.isoPath, "rb") as file:
            file.seek(32808, 0) # Go to Volume Descriptor (https://wiki.osdev.org/ISO_9660#The_Primary_Volume_Descriptor)
            self.isoName = file.read(32).decode("utf-8").strip() # Read 32 Bytes
    
    def formatDrive(self):
        # Unmount the drive before writing on it
        subprocess.run(["umount", "-lf" , self.drive+"1"])

        # Format USB to FAT32
        subprocess.run(["dd", "if=/dev/zero", "of={}".format(self.drive), "bs=512", "count=1"])
        subprocess.run(["parted", self.drive, "mktable", "msdos"])
        subprocess.run(["parted", self.drive, "mkpart", "primary", "fat32", "1", "100%"])
        subprocess.run(["wipefs", "-a", (self.drive+"1"), "--force"])
        subprocess.run(["mkfs.fat", "-F", "32", "-n", self.isoName, "-I", (self.drive+"1")])
        subprocess.run(["parted", self.drive, "set", "1", "boot", "on"])
        subprocess.run(["sync"])

    def mountFolders(self):
        # Unmount first if already mounted
        subprocess.run(["umount", self.isoTmpFolder])
        subprocess.run(["umount", self.usbMountFolder])
        subprocess.run(["umount", (self.drive+"1")])

        subprocess.run(["mkdir", self.isoTmpFolder])
        subprocess.run(["mount", "-o", "ro", "-t", "auto", self.isoPath, self.isoTmpFolder])

        subprocess.run(["mkdir", self.usbMountFolder])
        subprocess.run(["mount", (self.drive+"1"), self.usbMountFolder])
    
    def copyFiles(self):
        folders = os.listdir(self.isoTmpFolder)
        fileCount = len(folders)
        i=0
        for file in folders:
            subprocess.run(["rsync", "--archive", "--no-links", "--quiet", "--no-D", "--acls",
                self.isoTmpFolder + file, self.usbMountFolder])
            
            subprocess.run(["sync"])
            print("PROGRESS:{}:{}".format(i, fileCount))
            sys.stdout.flush()
            i += 1

        

    def installGrub(self):
        # Install GRUB
        subprocess.run(["grub-install", "--target=i386-pc", "--force" ,"--removable", "--boot-directory=/{}/boot".format(self.usbMountFolder), self.drive])
        subprocess.run(["sync"])
    
    def windowsISOAddition(self):
        with open(self.usbMountFolder + "/boot/grub/grub.cfg", "a") as grubcfg:
            grubcfg.write("ntldr /bootmgr\nchainloader +1\nboot")
    
    def finishEvent(self):
        # Unmount the temp folder
        subprocess.run(["umount", self.isoTmpFolder])
        subprocess.run(["umount", (self.drive+"1")])
        subprocess.run(["rm", "-rf", self.isoTmpFolder])
        subprocess.run(["rm", "-rf", self.usbMountFolder])

if __name__ == "__main__":
    # Iso write action
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: {} [iso path] [drive]\n".format(sys.argv[0]))
        exit(1)
    i=IsoCopy(sys.argv[1],sys.argv[2])
    i.run()

