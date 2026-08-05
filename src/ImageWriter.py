#!/usr/bin/python3
"""Raw (dd style) image writer for Pardus Image Writer.

This script is executed as root through pkexec, so every input coming from the
GUI is treated as untrusted and validated again here. The drive validation
itself lives in USBDeviceManager and is shared with ISOCopier.py.

stdout is a machine readable progress stream consumed by MainWindow:
one "<written_bytes> <total_bytes>" line per update, nothing else.
All diagnostics go to stderr.

Exit codes:
    0   image written successfully
    1   validation or I/O error
    killed by SIGTERM when the user cancels (MainWindow expects this)
"""

import os
import shutil
import signal
import stat
import subprocess
import sys

from USBDeviceManager import DriveError, open_drive_exclusive, validate_usb_drive
from USBDeviceManager import unmount_drive
from Utils import exit_as_cancelled, fail, log, open_as_caller, request_stop
from Utils import stop_requested, watch_stdin_for_cancel

BUFFER_SIZE = 4 * 1024 * 1024  # 4 MiB read/write chunk


def receive_stop_signal(number, frame):
    request_stop(number)


def open_image_file(filepath):
    """Open the image read-only and make sure it is a usable regular file.

    The open runs with the credentials of the user that invoked pkexec. This
    process is root and could otherwise be pointed at any file on the machine,
    and copying /etc/shadow onto a USB disk is not what the person answering
    the authentication prompt agreed to.

    O_NONBLOCK keeps the open from hanging forever on a FIFO or on a device
    node, and the type is checked on the descriptor itself, so the file cannot
    be swapped between the check and the read.
    """
    open_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        file_descriptor = open_as_caller(filepath, open_flags)
    except OSError as error:
        fail("Could not open the image file: {}".format(error))

    file_info = os.fstat(file_descriptor)
    if not stat.S_ISREG(file_info.st_mode):
        os.close(file_descriptor)
        fail("{} is not a regular file.".format(filepath))

    # O_NONBLOCK has no meaning for regular files, but do not leave it set.
    os.set_blocking(file_descriptor, True)
    image_file = os.fdopen(file_descriptor, "rb")

    if file_info.st_size == 0:
        image_file.close()
        fail("{} is empty.".format(filepath))

    return image_file, file_info.st_size


def write_image(image_file, drive_file, total_bytes):
    """Copy the image onto the drive, reporting progress on stdout.

    The drive is opened with O_DSYNC, so every write only returns once the data
    is on the stick. That makes each reported number the real progress of the
    disk, and there is no periodic flush that would stall the report.
    """
    written_bytes = 0

    print("0 {}".format(total_bytes))
    sys.stdout.flush()

    while not stop_requested():
        chunk = image_file.read(BUFFER_SIZE)
        if not chunk:
            break

        drive_file.write(chunk)
        drive_file.flush()
        written_bytes += len(chunk)

        print("{} {}".format(written_bytes, total_bytes))
        sys.stdout.flush()

    if stop_requested():
        return False

    drive_file.flush()
    os.fsync(drive_file.fileno())

    print("{} {}".format(total_bytes, total_bytes))
    sys.stdout.flush()

    return True


def eject_drive(drive):
    """Eject the drive. Failing to eject does not invalidate the written image."""
    eject = shutil.which("eject")
    if eject is None:
        log("Warning: eject command not found.")
        return

    result = subprocess.run(
        [eject, drive], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if result.returncode != 0:
        log("Warning: could not eject {}.".format(drive))


def main():
    # The third argument (is_windows) only applies to ISOCopier.py; accept and
    # ignore it so both scripts can be called with the same argument list.
    if len(sys.argv) not in (3, 4):
        sys.stderr.write("Usage: ./ImageWriter.py /file/path/iso.iso /dev/sdX\n")
        sys.exit(1)

    filepath = sys.argv[1]
    drive = sys.argv[2]

    # The image is validated first so a bad file never costs the user the
    # mounted filesystems of the drive.
    image_file, total_bytes = open_image_file(filepath)

    try:
        block_name = validate_usb_drive(drive)
        unmount_drive(drive, block_name)
        # O_DSYNC: without it the writes only reach the page cache, the
        # progress races ahead of the stick at RAM speed and then freezes on
        # every flush, and the reported speed is the speed of the memory.
        file_descriptor, drive_size = open_drive_exclusive(
            drive, block_name, sync_writes=True
        )
    except DriveError as error:
        image_file.close()
        fail(error)

    if total_bytes > drive_size:
        os.close(file_descriptor)
        image_file.close()
        fail(
            "The image is larger than the disk: {} bytes > {} bytes.".format(
                total_bytes, drive_size
            )
        )

    # From here on a cancel request must not kill the process mid write: the
    # handler only raises a flag and the write loop leaves the drive in a
    # flushed, consistent state before exiting. The GUI cancels by closing the
    # pipe on stdin, a signal only arrives when the script is used by hand.
    signal.signal(signal.SIGTERM, receive_stop_signal)
    signal.signal(signal.SIGINT, receive_stop_signal)
    watch_stdin_for_cancel()

    completed = False
    try:
        # Buffered on purpose: a BufferedWriter retries short writes, a raw
        # descriptor would silently drop the tail of a partially written chunk.
        with (
            image_file,
            os.fdopen(file_descriptor, "wb", buffering=BUFFER_SIZE) as drive_file,
        ):
            completed = write_image(image_file, drive_file, total_bytes)
    except OSError as error:
        fail("Writing failed: {}".format(error))

    if not completed:
        exit_as_cancelled()

    eject_drive(drive)
    sys.exit(0)


if __name__ == "__main__":
    main()
