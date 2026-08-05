#!/usr/bin/python3
"""USB device discovery and target drive validation.

The module has two layers:

* validation functions, which only read sysfs and /proc. They are used by the
  privileged writer scripts (ImageWriter.py, ISOCopier.py) to validate the drive
  they are about to destroy. They never terminate the process themselves: every
  rejection is raised as a DriveError so the caller can report it its own way.
* the device list of the GUI, which additionally needs pyudev for labels and
  hotplug events. Its udev context and monitoring thread are module level
  singletons, so importing the module costs nothing and no caller has to own
  or pass around a manager object.
"""

import os
import re
import shutil
import stat
import subprocess
from glob import glob

from pyudev import Context, Monitor, Devices
from pyudev import MonitorObserver, DeviceNotFoundAtPathError

# Never write to a disk that carries one of these mount points. The USB check
# already rejects the internal disk of a normal machine, but on the boards and
# mini PCs whose system disk sits behind a USB bridge this list is the only
# thing standing between the user and an unbootable system.
CRITICAL_MOUNT_POINTS = (
    "/",
    "/boot",
    "/boot/efi",
    "/efi",
    "/etc",
    "/home",
    "/opt",
    "/srv",
    "/tmp",
    "/usr",
    "/usr/local",
    "/var",
    "/var/log",
)


class DriveError(Exception):
    """The target drive is missing, unsafe or not a removable USB disk."""


def find_usb_block_names():
    """Return the /sys/block names of the connected USB disks, e.g. ['sdb']."""
    block_names = []
    for path in map(os.path.realpath, glob("/sys/block/sd*")):
        if any("usb" in part for part in path.split("/")):
            block_names.append(os.path.basename(path))

    return block_names


def get_block_name(drive):
    """Return the /sys/block name of a whole-disk device path, or None.

    Only plain '/dev/<name>' paths are accepted, so a crafted argument such as
    '/dev/../dev/sda' or '/dev/disk/by-id/...' can never reach a write.
    """
    directory, name = os.path.split(drive)
    if directory != "/dev" or not name or name in (".", ".."):
        return None

    if not os.path.isdir("/sys/block/{}".format(name)):
        return None

    return name


def get_partitions(block_name):
    """Return the partition device paths of a disk, e.g. ['/dev/sdb1', ...]."""
    partitions = []
    for path in glob("/sys/block/{}/{}*".format(block_name, block_name)):
        if os.path.isfile(os.path.join(path, "partition")):
            partitions.append("/dev/{}".format(os.path.basename(path)))

    return partitions


def unescape_mount_field(field):
    """/proc/self/mounts escapes space, tab, newline and backslash as octal."""
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def get_mounts():
    """Return the [(source, mount_point)] list of currently mounted filesystems.

    Sources are resolved, because a filesystem can be mounted through a symlink
    such as /dev/disk/by-uuid/... while it still lives on the target drive.
    """
    mounts = []
    with open("/proc/self/mounts", "r") as mounts_file:
        for line in mounts_file:
            fields = line.split()
            if len(fields) < 2:
                continue
            source = os.path.realpath(unescape_mount_field(fields[0]))
            mounts.append((source, unescape_mount_field(fields[1])))

    return mounts


def get_swap_devices():
    """Return the resolved device paths of the partitions used as swap.

    A swap partition never shows up in the mount table and umount cannot free
    it, so it has to be rejected rather than unmounted. /proc/swaps escapes its
    first field the same way /proc/self/mounts does.
    """
    devices = []
    try:
        with open("/proc/swaps", "r") as swaps_file:
            next(swaps_file, None)  # header line
            for line in swaps_file:
                fields = line.split()
                if len(fields) < 2 or fields[1] != "partition":
                    continue
                devices.append(os.path.realpath(unescape_mount_field(fields[0])))
    except OSError:
        pass

    return devices


def is_whole_usb_disk(major, minor, block_name):
    """Check in sysfs that a device number is the whole USB disk we validated.

    The lookup starts from the device number of an already opened descriptor,
    so it describes the disk that is really about to be written.
    """
    resolved = os.path.realpath("/sys/dev/block/{}:{}".format(major, minor))

    if os.path.basename(resolved) != block_name:
        return False

    # A partition carries a 'partition' attribute, a whole disk does not.
    if os.path.exists(os.path.join(resolved, "partition")):
        return False

    # The sysfs path of a USB disk walks through the USB bus, e.g.
    # /sys/devices/.../usb3/3-1/3-1:1.0/host0/target0:0:0/0:0:0:0/block/sda
    return any("usb" in part for part in resolved.split("/"))


def validate_usb_drive(drive):
    """Make sure the drive may be destroyed, and return its /sys/block name.

    Raises DriveError when the path is not a whole USB disk, when it carries a
    system mount point, when one of its partitions is active swap, or when it
    backs a device mapper target.
    """
    block_name = get_block_name(drive)
    if block_name is None:
        raise DriveError("{} is not a whole disk device path.".format(drive))

    if block_name not in find_usb_block_names():
        raise DriveError("{} is not a removable USB drive.".format(drive))

    device_paths = set([drive] + get_partitions(block_name))
    for source, mount_point in get_mounts():
        if source in device_paths and mount_point in CRITICAL_MOUNT_POINTS:
            raise DriveError(
                "{} carries the system mount point {}.".format(source, mount_point)
            )

    swap_devices = set(get_swap_devices())
    for device_path in sorted(device_paths & swap_devices):
        raise DriveError("{} is in use as swap space.".format(device_path))

    # A holder means the disk or one of its partitions is a backing device of a
    # device mapper target, so writing it would destroy a live stacked volume.
    holders = glob("/sys/block/{}/holders/*".format(block_name)) + glob(
        "/sys/block/{}/{}*/holders/*".format(block_name, block_name)
    )
    if holders:
        raise DriveError(
            "{} is in use by a device mapper layer (LVM, LUKS or RAID).".format(drive)
        )

    return block_name


def unmount_drive(drive, block_name):
    """Unmount every filesystem of the drive; writing under a mount corrupts it."""
    umount = shutil.which("umount")
    if umount is None:
        raise DriveError("umount command not found.")

    device_paths = set([drive] + get_partitions(block_name))
    for source, mount_point in get_mounts():
        if source not in device_paths:
            continue

        result = subprocess.run(
            [umount, source], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        if result.returncode != 0:
            reason = result.stderr.decode("utf-8", "replace").strip()
            raise DriveError(
                "Could not unmount {} from {}: {}".format(source, mount_point, reason)
            )


def open_drive_exclusive(drive, block_name, sync_writes=False):
    """Open the drive exclusively and re-verify it on the open descriptor.

    O_EXCL on a block device makes the kernel refuse the open if the disk is
    mounted or already held by someone else, and blocks any mount attempt while
    the descriptor is open. Checking the device number of the descriptor itself
    closes the gap between the name based checks above and the actual write.

    With sync_writes every write only returns once the data reached the disk,
    so the progress a caller reports is the real progress of the USB stick
    instead of the fill level of the page cache.

    Returns (file_descriptor, drive_size_in_bytes). The caller owns the
    descriptor and has to close it.
    """
    open_flags = os.O_WRONLY | os.O_EXCL | os.O_CLOEXEC
    if sync_writes:
        open_flags |= os.O_DSYNC

    try:
        file_descriptor = os.open(drive, open_flags)
    except OSError as error:
        raise DriveError("Could not open {} for writing: {}".format(drive, error))

    try:
        device_info = os.fstat(file_descriptor)
        if not stat.S_ISBLK(device_info.st_mode):
            raise DriveError("{} is not a block device.".format(drive))

        major = os.major(device_info.st_rdev)
        minor = os.minor(device_info.st_rdev)
        if not is_whole_usb_disk(major, minor, block_name):
            raise DriveError("{} is not a whole USB disk.".format(drive))

        drive_size = os.lseek(file_descriptor, 0, os.SEEK_END)
        os.lseek(file_descriptor, 0, os.SEEK_SET)
    except (DriveError, OSError):
        os.close(file_descriptor)
        raise

    return file_descriptor, drive_size


def prepare_usb_drive(drive):
    """Validate and unmount the drive, then return (block_name, size_in_bytes).

    The exclusive descriptor is only used to prove that nothing else holds the
    disk and is closed again, so callers that drive external tools such as
    parted can keep working on the device afterwards.
    """
    block_name = validate_usb_drive(drive)
    unmount_drive(drive, block_name)

    file_descriptor, drive_size = open_drive_exclusive(drive, block_name)
    os.close(file_descriptor)

    return block_name, drive_size


def reassert_usb_drive(drive, block_name):
    """Validate the drive again right before it is destroyed.

    ISO mode has to hand the disk over to parted and mkfs, so unlike the raw
    writer it cannot hold the exclusive descriptor for the whole run. Checking
    again immediately before the partition table is wiped shrinks the window in
    which the disk could have been unplugged, replaced or mounted down to the
    few milliseconds it takes to get from here to the first write.
    """
    current_block_name = validate_usb_drive(drive)
    if current_block_name != block_name:
        raise DriveError("{} is no longer the disk that was validated.".format(drive))

    unmount_drive(drive, block_name)

    file_descriptor, _drive_size = open_drive_exclusive(drive, block_name)
    os.close(file_descriptor)


def read_sysfs_int(path):
    """Read a single integer out of a sysfs attribute."""
    with open(path, "r") as attribute_file:
        return int(attribute_file.readline())


def format_size(size):
    """Format a byte count the way disk vendors do, e.g. '32GB'."""
    for limit, unit in (
        (1000000000000, "TB"),
        (1000000000, "GB"),
        (1000000, "MB"),
        (1000, "kB"),
    ):
        if size >= limit:
            return "%.0f%s" % (round(size / limit), unit)

    return "%.0fB" % round(size)


# The udev context, monitor and observer are process wide singletons: one udev
# connection and one monitoring thread are enough no matter how many callers
# the module has.
_context = None
_monitor = None
_observer = None
_refresh_callbacks = []


def get_context():
    """Return the shared udev context, creating it on first use."""
    global _context

    if _context is None:
        _context = Context()

    return _context


def _on_udev_event(action, device):
    # Runs in the observer thread; callbacks that touch a GUI have to hand the
    # work back to their own main loop themselves.
    for callback in _refresh_callbacks:
        callback()


def connect_usb_refresh_signal(signalfunc):
    """Call signalfunc whenever a block device is plugged in or removed."""
    global _monitor, _observer

    _refresh_callbacks.append(signalfunc)

    if _observer is None:
        _monitor = Monitor.from_netlink(get_context())
        _monitor.filter_by(subsystem="block", device_type="disk")
        _observer = MonitorObserver(_monitor, _on_udev_event)
        _observer.start()


def get_usb_devices():
    """Return [[name, label, size]] for every connected USB disk."""
    context = get_context()
    deviceList = []

    for blockName in find_usb_block_names():
        try:
            device = Devices.from_path(context, "/sys/block/{}".format(blockName))

            # 'FEDAR32', or 'Kingston DataTraveler' when there is no label
            deviceLabel = device.get("ID_FS_LABEL", "")
            if deviceLabel == "":
                deviceLabel = "{} {}".format(
                    device.get("ID_VENDOR", ""), device.get("ID_MODEL", "NO_MODEL")
                )

            blockCount = read_sysfs_int("/sys/block/{}/size".format(blockName))
            blockSize = read_sysfs_int(
                "/sys/block/{}/queue/logical_block_size".format(blockName)
            )
        except (DeviceNotFoundAtPathError, OSError, ValueError):
            # The device was unplugged while its attributes were read.
            continue

        if blockCount > 0:
            deviceList.append(
                [blockName, deviceLabel, format_size(blockCount * blockSize)]
            )

    return deviceList
