#!/usr/bin/python3
"""ISO mode writer: partition the USB disk and copy the ISO contents onto it.

Like ImageWriter.py this script is executed as root through pkexec, so the
target drive is validated with the shared helpers in USBDeviceManager before
anything destructive happens. No command line is ever built through a shell.

stdout carries the progress protocol MainWindow parses (TOTAL_BYTES:, BYTES:,
COPIED:); everything else goes to stderr.
"""

import math
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from subprocess import Popen, PIPE

from USBDeviceManager import DriveError, prepare_usb_drive, read_sysfs_int
from USBDeviceManager import reassert_usb_drive, unmount_drive
from Utils import CancelledError, exit_as_cancelled, fail, log, open_as_caller
from Utils import request_stop, run, settle, stop_requested, sync
from Utils import wait_for_block_device, watch_stdin_for_cancel

UEFI_PARTITION_SIZE = 200 * 1024 * 1024  # 200MB EFI partition for Windows mode

# Everything this script mounts lives below one private directory. The
# permissions of a mounted filesystem come from its own root inode, so the
# mount points themselves cannot be locked down; a 0700 root owned parent makes
# the whole subtree unreachable for every other local user instead.
RUNTIME_DIRECTORY = "/run/pardus-image-writer"

# The ISO is a file the user picked, so the kernel parses a filesystem of
# unknown origin as root. Without these options a crafted image could ship a
# setuid root binary or a device node, and while the copy runs any local user
# would be able to use it.
MOUNT_OPTIONS = "nosuid,nodev,noexec"

# parted aligns the first partition at 1MB and a filesystem needs room for its
# own metadata, so an ISO that is only just smaller than the disk still does
# not fit.
PARTITION_ALIGNMENT = 1024 * 1024
FILESYSTEM_OVERHEAD = 1.02


class IsoCopy:
    def __init__(self, iso_path, drive, is_windows=False):
        # Define file variables
        self.iso_mounted_path = os.path.join(RUNTIME_DIRECTORY, "iso")
        self.usb_mounted_path = os.path.join(RUNTIME_DIRECTORY, "usb")
        self.iso_file_path = iso_path  # e.g. "/home/user/Downloads/pardus.iso"
        self.drive = drive  # e.g. "/dev/sdb"

        # Variables
        self.spawned_process = None
        self.exit_code = 0
        self.cancelled = False
        self.is_windows = is_windows

        # Kept open for the whole run so the inode that was accepted cannot be
        # replaced by another one afterwards.
        self.iso_descriptor, self.iso_size = self.open_iso_file(iso_path)

        # Validate, unmount and claim the drive before a single byte is touched.
        try:
            self.block_name, self.drive_size = prepare_usb_drive(drive)
        except DriveError as error:
            fail(error)

        self.check_iso_fits()

        self.sector_size = read_sysfs_int(
            "/sys/block/{}/queue/logical_block_size".format(self.block_name)
        )

        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        # The GUI runs as the user and cannot signal a root process, so it
        # cancels by closing the pipe it holds on stdin.
        watch_stdin_for_cancel(self.stop_spawned_process)

    def open_iso_file(self, iso_path):
        """Open the ISO and make sure it is a real, non empty file.

        The open runs with the credentials of the user that invoked pkexec:
        this process is root, and a write is only ever meant to be started for
        a file the caller could have read on their own.

        O_NONBLOCK keeps the open from hanging on a FIFO, and the type is
        checked on the descriptor itself rather than on the path.
        """
        open_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
        try:
            file_descriptor = open_as_caller(iso_path, open_flags)
        except OSError as error:
            fail("Could not read the ISO file: {}".format(error))

        file_info = os.fstat(file_descriptor)

        if not stat.S_ISREG(file_info.st_mode):
            os.close(file_descriptor)
            fail("{} is not a regular file.".format(iso_path))

        if file_info.st_size == 0:
            os.close(file_descriptor)
            fail("{} is empty.".format(iso_path))

        return file_descriptor, file_info.st_size

    def check_iso_fits(self):
        """Reject an oversized image while the disk is still intact.

        Without this the partition table is wiped first and the copy only runs
        out of space minutes later, leaving the user with neither the old
        content of the disk nor a usable one.
        """
        required_bytes = int(self.iso_size * FILESYSTEM_OVERHEAD) + PARTITION_ALIGNMENT
        if self.is_windows:
            required_bytes += UEFI_PARTITION_SIZE

        if required_bytes > self.drive_size:
            fail(
                "The ISO does not fit on the disk: {} bytes needed, {} available.".format(
                    required_bytes, self.drive_size
                )
            )

    def stop_spawned_process(self):
        if self.spawned_process:
            self.spawned_process.kill()

    def signal_handler(self, number, frame):
        request_stop(number)
        self.stop_spawned_process()

    def start_writing(self):
        try:
            # Last chance to notice that the disk was swapped, unplugged or
            # mounted between the checks in __init__ and the first write.
            reassert_usb_drive(self.drive, self.block_name)

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

        except CancelledError:
            self.cancelled = True
        except (OSError, subprocess.CalledProcessError, DriveError) as error:
            log("Exception happened: {}".format(error))
            self.exit_code = 1
        finally:
            self.finish_writing()

        if self.cancelled:
            exit_as_cancelled()

        if self.exit_code:
            sys.exit(self.exit_code)

    def create_partition_table(self, drive):
        # Delete old partitions
        run(["dd", "if=/dev/zero", "of={}".format(drive), "bs=1M", "count=1"])
        run(["parted", drive, "mktable", "msdos"])

    def wait_for_partition(self, partition):
        """parted returns before udev created the node mkfs is about to use."""
        settle()
        if not wait_for_block_device(partition):
            raise DriveError("{} did not appear after partitioning.".format(partition))

    def create_fat32_partition(self, drive):
        partition1 = "{}1".format(drive)

        # Create FAT32, bootable
        run(["parted", drive, "mkpart", "primary", "fat32", "1", "100%"])
        self.wait_for_partition(partition1)

        # Wipe the old one
        run(["wipefs", "-a", partition1, "--force"], False)

        run(["mkfs.vfat", partition1])
        run(["parted", drive, "set", "1", "boot", "on"])  # bios boot support

    def create_windows_partitions(self, drive):
        partition1 = "{}1".format(drive)
        partition2 = "{}2".format(drive)

        total_sectors = int(self.drive_size / self.sector_size)
        uefi_sectors = math.ceil(UEFI_PARTITION_SIZE / self.sector_size)
        ntfs_sector_end = total_sectors - uefi_sectors - 1

        if ntfs_sector_end < 1:
            raise DriveError("{} is too small for Windows mode.".format(drive))

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
                "{}s".format(ntfs_sector_end),
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
                "{}s".format(ntfs_sector_end + 1),
                "100%",
            ]
        )
        self.wait_for_partition(partition1)
        self.wait_for_partition(partition2)

        run(["wipefs", "-a", partition1, "--force"], False)
        run(["wipefs", "-a", partition2, "--force"], False)

        run(["mkfs.ntfs", "-f", "-v", partition1])
        run(["mkfs.fat", "-F32", partition2])

        run(["parted", drive, "set", "1", "boot", "on"])

        # Create UEFI supports file NTFS format on partition2
        # uefi image url: "https://github.com/pbatard/rufus/raw/master/res/uefi/assets/uefi-ntfs.img",
        uefi_ntfs_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "assets", "uefi-ntfs.img"
        )
        if not os.path.isfile(uefi_ntfs_path):
            raise DriveError("UEFI helper image not found: {}".format(uefi_ntfs_path))

        run(["dd", "if={}".format(uefi_ntfs_path), "of={}".format(partition2)])

        run(["parted", drive, "set", "2", "hidden", "on"])
        run(["parted", drive, "set", "2", "esp", "on"])

        sync()

    def create_runtime_directory(self):
        """Create the private 0700 directory both mount points live in."""
        if os.path.islink(RUNTIME_DIRECTORY):
            raise DriveError("{} is a symbolic link.".format(RUNTIME_DIRECTORY))

        os.makedirs(RUNTIME_DIRECTORY, mode=0o700, exist_ok=True)
        # makedirs only applies the mode when it creates the directory, and the
        # umask can take bits off even then.
        os.chown(RUNTIME_DIRECTORY, 0, 0)
        os.chmod(RUNTIME_DIRECTORY, 0o700)

        os.makedirs(self.iso_mounted_path, mode=0o700, exist_ok=True)
        os.makedirs(self.usb_mounted_path, mode=0o700, exist_ok=True)

    def mount_folders(self, drive):
        partition1 = "{}1".format(drive)

        # Unmount first if already mounted
        self.unmount_tmp_folders()
        self.remove_tmp_folders()

        # The desktop may have auto mounted the partitions we just created.
        unmount_drive(drive, self.block_name)

        self.create_runtime_directory()

        # Mount ISO Image
        run(
            [
                "mount",
                "-o",
                "ro," + MOUNT_OPTIONS,
                "-t",
                "udf" if self.is_windows else "iso9660",
                self.iso_file_path,
                self.iso_mounted_path,
            ]
        )

        # Mount USB
        run(
            [
                "mount",
                "-o",
                "rw," + MOUNT_OPTIONS,
                "-t",
                "ntfs3" if self.is_windows else "vfat",
                partition1,
                self.usb_mounted_path,
            ]
        )

    def copy_dir_with_dd(self, src, dest):
        sync()

        copy_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "copy_dir_with_dd.sh"
        )

        with Popen(
            [copy_script, src, dest],
            stdout=PIPE,
            # pv reports the copied byte counts on stderr, so it has to be
            # merged into the stream we read.
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        ) as process:
            self.spawned_process = process
            for line in process.stdout:
                if stop_requested():
                    process.kill()
                    break

                # The script reports plain byte counts, everything else is a
                # protocol line of its own (TOTAL_BYTES:, COPIED:).
                if line.strip().isdigit():
                    sys.stdout.write("BYTES:{}".format(line))
                else:
                    sys.stdout.write(line)
                sys.stdout.flush()

        self.spawned_process = None

        if stop_requested():
            raise CancelledError()

        # Without this check a half copied USB disk would get a boot loader and
        # be reported as finished.
        if process.returncode != 0:
            raise DriveError(
                "Copying the ISO contents failed with exit code {}.".format(
                    process.returncode
                )
            )

        sync()

    def install_grub(self, drive, usb_mounted_path):
        sync()

        boot_directory = os.path.join(usb_mounted_path, "boot")

        if self.is_windows:
            run(
                [
                    "grub-install",
                    drive,
                    "--target=i386-pc",
                    "--force",
                    "--boot-directory={}".format(boot_directory),
                ]
            )
            return

        # Remove grub & efi information on copied ISO file data:
        shutil.rmtree(os.path.join(boot_directory, "grub"), ignore_errors=True)
        shutil.rmtree(os.path.join(usb_mounted_path, "EFI"), ignore_errors=True)

        # Install new grub on efi partition
        run(
            [
                "grub-install",
                "--target=i386-pc",
                "--efi-directory={}".format(usb_mounted_path),
                "--boot-directory={}".format(boot_directory),
                drive,
            ]
        )
        run(
            [
                "grub-install",
                "--target=x86_64-efi",
                "--removable",
                "--efi-directory={}".format(usb_mounted_path),
                "--boot-directory={}".format(boot_directory),
                drive,
            ]
        )
        run(["grub-install", "--recheck", drive])

    def windows_iso_addition(self, usb_mounted_path):
        grub_cfg_path = os.path.join(usb_mounted_path, "boot", "grub", "grub.cfg")
        with open(grub_cfg_path, "a") as grubcfg:
            grubcfg.write("insmod part_msdos\n")
            grubcfg.write("insmod ntfs\n")
            grubcfg.write("insmod ntldr\n")
            grubcfg.write("ntldr /bootmgr\n")
            grubcfg.write("boot\n")

    def finish_writing(self):
        # Runs while unwinding an error or a cancel too, so it must not raise.
        for command in (
            ["sync"],
            ["umount", self.iso_mounted_path],
            ["umount", self.usb_mounted_path],
            ["umount", "{}1".format(self.drive)],
        ):
            subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        shutil.rmtree(RUNTIME_DIRECTORY, ignore_errors=True)

    def unmount_tmp_folders(self):
        run(["umount", self.iso_mounted_path], False)
        run(["umount", self.usb_mounted_path], False)

    def remove_tmp_folders(self):
        shutil.rmtree(self.iso_mounted_path, ignore_errors=True)
        shutil.rmtree(self.usb_mounted_path, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.stderr.write(
            "Usage: {} [iso path] [drive] [is_windows=false]\n".format(sys.argv[0])
        )
        sys.exit(1)

    is_windows = len(sys.argv) == 4 and sys.argv[3] == "true"

    IsoCopy(sys.argv[1], sys.argv[2], is_windows=is_windows).start_writing()
