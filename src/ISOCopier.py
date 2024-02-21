#!/usr/bin/python3

import os
import re
import signal
import stat
import subprocess
from subprocess import Popen, PIPE
import sys


def run(cmd, vital=True):
    subprocess.run(cmd, check=vital)


def sync():
    run(["sync"])


def file_count(dir):
    return len([1 for x in list(os.scandir(dir))])


class IsoCopy:
    def error(self, msg=""):
        sys.stderr.write("\x1b[31;1mError: \x1b[;0m{}".format(msg))
        exit(8)

    def signal_handler(self, number, frame):
        print("----SIGNAL RECEIVED----")
        print(self.dd_process)
        self.signal_received = number
        if self.dd_process:
            self.dd_process.kill()

    def __init__(self, iso_path, drive):
        # Define variables with fallback
        self.iso_mounted_path = "/run/pardus-iso-tmp/"
        self.usb_mounted_path = "/run/pardus-usb-tmp/"
        self.iso_file_path = iso_path  # e.g. "/home/user/Downloads/pardus.iso"
        self.drive = drive  # e.g. "/dev/sdb"
        self.iso_name = ""
        self.dd_process = None
        self.signal_received = None
        self.exit_code = 0

        signal.signal(signal.SIGTERM, self.signal_handler)

        # Check variables
        if not os.path.isfile(iso_path):
            self.error("ISO file not found")
        if not stat.S_ISBLK(os.stat(drive).st_mode):
            self.error("{} is not a valid block device".format(drive))

    def start_writing(self):
        try:
            self.read_iso_name()
            self.create_partition_table()
            self.create_fat32_partition()

            self.mount_folders()

            self.copy_dir_with_dd(self.iso_mounted_path, self.usb_mounted_path)

            self.install_grub()
        except Exception as e:
            print(f"Exception happened: {e}")
            if e == "Cancel":
                self.exit_code = 0
            else:
                self.exit_code = 1
        finally:
            sync()
            self.finish_writing()

        if self.exit_code:
            exit(self.exit_code)

    def read_iso_name(self):
        with open(self.iso_file_path, "rb") as file:
            file.seek(
                32808, 0
            )  # Go to Volume Descriptor (https://wiki.osdev.org/ISO_9660#The_Primary_Volume_Descriptor)
            self.iso_name = file.read(32).decode("utf-8").strip()  # Read 32 Bytes

        # print("read_iso_name()")

    def create_partition_table(self):
        # Unmount the drive before writing on it
        run(["sh", "-c", ("ls {}* | xargs umount -lf ".format(self.drive))], False)

        # Delete old partitions
        run(["dd", "if=/dev/zero", "of={}".format(self.drive), "bs=1M", "count=1"])
        run(["parted", self.drive, "mktable", "msdos"])

        sync()

        # print("create_partition_table()")

    def create_fat32_partition(self):
        partition1 = f"{self.drive}1"
        # Create FAT32, bootable
        run(["parted", self.drive, "mkpart", "primary", "fat32", "1", "100%"])

        # Wipe the old one
        run(["wipefs", "-a", partition1, "--force"])

        run(["mkfs.vfat", partition1])
        # run(
        #     ["parted", self.drive, "set", "1", "esp", "on"]
        # )  # EFI System Partition(esp) partition flag
        run(["parted", self.drive, "set", "1", "boot", "on"])  # bios boot support

        sync()

        # print("create_partitions()")

    def mount_folders(self):
        # Unmount first if already mounted
        self.unmount_tmp_folders()
        self.remove_tmp_folders()

        sync()

        # Mount ISO Image
        run(["mkdir", self.iso_mounted_path])
        run(
            [
                "mount",
                "-o",
                "ro",
                "-t",
                "iso9660",
                self.iso_file_path,
                self.iso_mounted_path,
            ]
        )

        # Mount USB
        run(["mkdir", self.usb_mounted_path])
        run(
            [
                "mount",
                "-o",
                "rw",
                "-t",
                "vfat",
                (self.drive + "1"),
                self.usb_mounted_path,
            ]
        )
        sync()

        # print("mount_folders()")

    def copy_dir_with_dd(self, src, dest):
        regex_only_number = re.compile(r"^(\d+)$")

        with Popen(
            [
                f"{os.path.dirname(os.path.abspath(__file__))}/copy_dir_with_dd.sh",
                src,
                dest,
            ],
            stdout=PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        ) as process:
            self.dd_process = process
            for line in process.stdout:
                if self.signal_received:
                    process.kill()
                    raise Exception("Cancel")

                if regex_only_number.match(line):
                    sys.stdout.write(f"BYTES:{line}")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(line)
                    sys.stdout.flush()

        sync()

        print("copy_dir_with_dd()")

    def install_grub(self):
        # Remove grub & efi information on copied ISO file data:
        run(
            [
                "rm",
                "-rf",
                "/{}/boot/grub".format(self.usb_mounted_path),
            ]
        )
        run(["rm", "-rf", "/{}/EFI".format(self.usb_mounted_path)])

        # Install new grub on efi partition
        run(
            [
                "grub-install",
                "--target=i386-pc",
                "--efi-directory=/{}/".format(self.usb_mounted_path),
                "--boot-directory=/{}/boot".format(self.usb_mounted_path),
                self.drive,
            ]
        )
        run(
            [
                "grub-install",
                "--target=x86_64-efi",
                "--removable",
                "--efi-directory=/{}/".format(self.usb_mounted_path),
                "--boot-directory=/{}/boot".format(self.usb_mounted_path),
                self.drive,
            ]
        )
        run(
            [
                "grub-install",
                "--recheck",
                self.drive,
            ]
        )

        sync()

    def finish_writing(self):
        self.unmount_tmp_folders(True)
        self.remove_tmp_folders(True)

        print("finish_writing()")

    def unmount_tmp_folders(self, vital=False):
        # Unmount the temp folder
        run(["umount", self.iso_mounted_path], vital)
        run(["umount", self.usb_mounted_path], vital)

        run(["umount", f"{self.drive}1"], False)

        sync()
        print("unmount_tmp_folders()")

    def remove_tmp_folders(self, vital=False):
        run(["rm", "-rf", self.iso_mounted_path], vital)
        run(["rm", "-rf", self.usb_mounted_path], vital)

        sync()
        print("remove_tmp_folders()")


if __name__ == "__main__":
    # Iso write action
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: {} [iso path] [drive]\n".format(sys.argv[0]))
        exit(1)

    i = IsoCopy(sys.argv[1], sys.argv[2])
    i.start_writing()
