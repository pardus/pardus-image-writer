#!/usr/bin/python3

import os
import re
import signal
import stat
import subprocess
from subprocess import Popen, PIPE
import sys
import math
import time


SIGNAL_RECEIVED = 0


def run(cmd, vital=True):
    if SIGNAL_RECEIVED:
        raise Exception("Stop signal received")
    else:
        subprocess.run(cmd, check=vital)


def file_count(dir):
    return len([1 for x in list(os.scandir(dir))])


def get_total_drive_size_bytes(drive):
    return int(
        subprocess.getoutput(
            f"parted {drive} 'unit B print' --machine | sed -n '2p' | cut -d ':' -f 2"
        )[:-1]
    )


def get_sector_size_bytes(drive):
    return int(
        subprocess.getoutput(
            f"parted {drive} 'unit B print' --machine | sed -n '2p' | cut -d ':' -f 4"
        )
    )


def sync():
    run(["sync"])


class IsoCopy:
    def error(self, msg=""):
        sys.stderr.write("\x1b[31;1mError: \x1b[;0m{}".format(msg))
        exit(8)

    def signal_handler(self, number, frame):
        global SIGNAL_RECEIVED

        print("----SIGNAL RECEIVED----")
        print(self.spawned_process)
        SIGNAL_RECEIVED = number
        if self.spawned_process:
            self.spawned_process.kill()

    def __init__(self, iso_path, drive, is_windows=False):
        # Define file variables
        self.iso_mounted_path = "/run/pardus-iso-tmp/"
        self.usb_mounted_path = "/run/pardus-usb-tmp/"
        self.iso_file_path = iso_path  # e.g. "/home/user/Downloads/pardus.iso"
        self.drive = drive  # e.g. "/dev/sdb"

        # Variables
        self.iso_name = ""
        self.spawned_process = None
        self.exit_code = 0
        self.is_windows = is_windows
        print("is_windows:", self.is_windows)

        signal.signal(signal.SIGTERM, self.signal_handler)

        # Check variables
        if not os.path.isfile(iso_path):
            self.error("ISO file not found")
        if not stat.S_ISBLK(os.stat(drive).st_mode):
            self.error("{} is not a valid block device".format(drive))

    def start_writing(self):
        try:
            self.iso_name = self.read_iso_name(self.iso_file_path)
            self.create_partition_table(self.drive)

            if self.is_windows:
                self.create_windows_partitions(self.drive)
            else:
                self.create_fat32_partition(self.drive)

            self.mount_folders(self.drive)

            self.copy_dir_with_dd(self.iso_mounted_path, self.usb_mounted_path)

            if self.is_windows:
                time.sleep(2)

            self.install_grub(self.drive, self.usb_mounted_path)

            if self.is_windows:
                self.windows_iso_addition(self.usb_mounted_path)

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

    def read_iso_name(self, iso_file_path):
        with open(iso_file_path, "rb") as file:
            file.seek(
                32808, 0
            )  # Go to Volume Descriptor (https://wiki.osdev.org/ISO_9660#The_Primary_Volume_Descriptor)
            return file.read(32).decode("utf-8").strip()  # Read 32 Bytes

        # print("read_iso_name()")

    def create_partition_table(self, drive):
        # Unmount the drive before writing on it
        run(["sh", "-c", ("ls {}* | xargs umount -lf ".format(drive))], False)

        # Delete old partitions
        run(["dd", "if=/dev/zero", "of={}".format(drive), "bs=1M", "count=1"])
        run(["parted", drive, "mktable", "msdos"])

        # print("create_partition_table()")

    def create_fat32_partition(self, drive):
        partition1 = f"{drive}1"
        # Create FAT32, bootable
        run(["parted", drive, "mkpart", "primary", "fat32", "1", "100%"])

        # Wipe the old one
        run(["wipefs", "-a", partition1, "--force"], False)

        run(["mkfs.vfat", partition1])
        run(["parted", drive, "set", "1", "boot", "on"])  # bios boot support

        # print("create_partitions()")

    def create_windows_partitions(self, drive):
        partition1 = f"{drive}1"
        partition2 = f"{drive}2"

        total_drive_size = get_total_drive_size_bytes(drive)
        sector_size = get_sector_size_bytes(drive)
        total_sectors = int(total_drive_size / sector_size)

        uefi_sector_size = math.ceil(200 * 1024 * 1024 / sector_size)  # 200MB uefi size
        ntfs_sector_end = total_sectors - uefi_sector_size - 1

        # Create NTFS partition1 (windows iso files here)
        run(
            [
                "parted",
                "-a",
                "minimal",
                drive,
                "mkpart",
                "primary",
                "ntfs",
                "1s",  # bootable needs to start from sector 1
                f"{ntfs_sector_end}s",
            ]
        )

        # Create FAT32 partition2 (uefi here)
        run(
            [
                "parted",
                "-a",
                "minimal",
                drive,
                "mkpart",
                "primary",
                "fat32",
                f"{ntfs_sector_end+1}s",
                "100%",
            ]
        )
        run(["wipefs", "-a", partition1, "--force"], False)
        run(["wipefs", "-a", partition2, "--force"], False)

        run(["mkfs.ntfs", "-f", "-v", partition1])
        run(["mkfs.fat", "-F32", partition2])

        run(["parted", drive, "set", "1", "boot", "on"])

        # Create UEFI supports file NTFS format on partition2
        # uefi image url: "https://github.com/pbatard/rufus/raw/master/res/uefi/assets/uefi-ntfs.img",
        uefi_ntfs_path = (
            os.path.dirname(os.path.abspath(__file__)) + "/../assets/uefi-ntfs.img"
        )

        run(["dd", f"if={uefi_ntfs_path}", f"of={partition2}"])

        run(["parted", drive, "set", "2", "hidden", "on"])
        run(["parted", drive, "set", "2", "esp", "on"])

        sync()

        # print("create_partitions()")

    def mount_folders(self, drive):
        partition1 = f"{drive}1"

        # Unmount first if already mounted
        self.unmount_tmp_folders()
        self.remove_tmp_folders()

        # Mount ISO Image
        run(["mkdir", self.iso_mounted_path])
        run(
            [
                "mount",
                "-o",
                "ro",
                "-t",
                "udf" if self.is_windows else "iso9660",
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
                "ntfs3" if self.is_windows else "vfat",
                partition1,
                self.usb_mounted_path,
            ]
        )

        # print("mount_folders()")

    def copy_dir_with_dd(self, src, dest):
        global SIGNAL_RECEIVED

        sync()

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
            self.spawned_process = process
            for line in process.stdout:
                if SIGNAL_RECEIVED:
                    process.kill()
                    sys.stdout.write("Copy Process killed.")
                    sys.stdout.flush()
                    break

                if regex_only_number.match(line):
                    sys.stdout.write(f"BYTES:{line}")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(line)
                    sys.stdout.flush()

        sync()

        print("copy_dir_with_dd()")

    def install_grub(self, drive, usb_mounted_path):
        sync()
        print("synced before grub installation")
        sys.stdout.flush()

        if self.is_windows:
            run(
                [
                    "grub-install",
                    drive,
                    "--target=i386-pc",
                    "--force",
                    f"--boot-directory=/{usb_mounted_path}/boot",
                ]
            )
            print("windows grub installed")
        else:
            # Remove grub & efi information on copied ISO file data:
            run(
                [
                    "rm",
                    "-rf",
                    f"/{usb_mounted_path}/boot/grub",
                ]
            )
            run(["rm", "-rf", f"/{usb_mounted_path}/EFI"])

            # Install new grub on efi partition
            run(
                [
                    "grub-install",
                    "--target=i386-pc",
                    f"--efi-directory=/{usb_mounted_path}/",
                    f"--boot-directory=/{usb_mounted_path}/boot",
                    drive,
                ]
            )
            run(
                [
                    "grub-install",
                    "--target=x86_64-efi",
                    "--removable",
                    f"--efi-directory=/{usb_mounted_path}/",
                    f"--boot-directory=/{usb_mounted_path}/boot",
                    drive,
                ]
            )
            run(
                [
                    "grub-install",
                    "--recheck",
                    drive,
                ]
            )

    def windows_iso_addition(self, usb_mounted_path):
        with open(usb_mounted_path + "/boot/grub/grub.cfg", "a") as grubcfg:
            grubcfg.write("insmod part_msdos\n")
            grubcfg.write("insmod ntfs\n")
            grubcfg.write("insmod ntldr\n")
            grubcfg.write("ntldr /bootmgr\n")
            grubcfg.write("boot\n")

    def finish_writing(self):
        self.unmount_tmp_folders(True)
        self.remove_tmp_folders(True)

        print("finish_writing()")

    def unmount_tmp_folders(self, vital=False):
        # Unmount the temp folder
        run(["umount", self.iso_mounted_path], vital)
        run(["umount", self.usb_mounted_path], vital)

        run(["umount", f"{self.drive}1"], False)

        print("unmount_tmp_folders()")

    def remove_tmp_folders(self, vital=False):
        run(["rm", "-rf", self.iso_mounted_path], vital)
        run(["rm", "-rf", self.usb_mounted_path], vital)

        print("remove_tmp_folders()")


if __name__ == "__main__":
    # Iso write action
    if len(sys.argv) < 2:
        sys.stderr.write(
            "Usage: {} [iso path] [drive] [is_windows=false]\n".format(sys.argv[0])
        )
        exit(1)

    is_windows = True if len(sys.argv) == 4 and sys.argv[3] == "true" else False
    print(f"is_windows = {is_windows}")
    print(f"sys.argv = {sys.argv}")

    i = IsoCopy(sys.argv[1], sys.argv[2], is_windows=is_windows)
    i.start_writing()
