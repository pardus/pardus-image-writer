#!/usr/bin/python3
"""Helpers shared by the privileged writer scripts.

ImageWriter.py and ISOCopier.py both talk to MainWindow through a progress
protocol on stdout, so every diagnostic has to go to stderr, both run external
commands without a shell, and both end a cancelled run the same way.

The stop flag lives here as well: a signal handler only records the request,
and the writers decide where it is safe to act on it. The same flag is raised
when the GUI closes the pipe it holds on stdin, which is how a cancel arrives
now that no polkit action for kill is shipped any more.
"""

import os
import pwd
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time

_stop_signal = 0


class CancelledError(Exception):
    """The user asked to stop, the run has to unwind and clean up."""


def request_stop(number=signal.SIGTERM):
    """Record a stop request. Safe to call from a signal handler."""
    global _stop_signal
    _stop_signal = number


def stop_requested():
    """True once a stop signal has been received."""
    return _stop_signal != 0


def log(message):
    """Write a diagnostic line. stdout belongs to the progress protocol."""
    sys.stderr.write("{}\n".format(message))
    sys.stderr.flush()


def fail(message):
    """Report an error and exit with 1, which MainWindow shows as a failure."""
    log("Error: {}".format(message))
    sys.exit(1)


def caller_uid():
    """Return the uid of the user that invoked pkexec, or None.

    pkexec exports PKEXEC_UID, so a script started through it can tell who
    asked for the work even though it runs as root. None means the script was
    started as root some other way, and then there is nobody to drop to.
    """
    value = os.environ.get("PKEXEC_UID", "")
    if not value.isdigit():
        return None

    uid = int(value)
    if uid == 0:
        return None

    return uid


def open_as_caller(path, flags):
    """Open a path with the credentials of the user that invoked pkexec.

    Both writers run as root, so without this they would happily open any file
    on the machine and copy it onto a USB disk the caller owns. A write is only
    ever meant to be started for a file the caller could have read themselves,
    and the kernel is the only thing that can decide that reliably, so the
    effective credentials are dropped around the open instead of the path being
    inspected.

    The real uid stays 0 and the saved uid is set to 0, which is what makes the
    restore below possible. Supplementary groups are set too, otherwise a file
    the caller reaches through a group would be rejected.
    """
    uid = caller_uid()
    if uid is None or os.geteuid() != 0:
        return os.open(path, flags)

    try:
        entry = pwd.getpwuid(uid)
        groups = os.getgrouplist(entry.pw_name, entry.pw_gid)
    except KeyError:
        raise PermissionError("Unknown calling user id {}.".format(uid))

    saved_groups = os.getgroups()
    try:
        os.setgroups(groups)
        os.setresgid(-1, entry.pw_gid, 0)
        os.setresuid(-1, uid, 0)

        return os.open(path, flags)
    finally:
        os.setresuid(-1, 0, 0)
        os.setresgid(-1, 0, 0)
        os.setgroups(saved_groups)


def watch_stdin_for_cancel(on_cancel=None):
    """Raise the stop flag when the GUI closes the pipe it holds on stdin.

    The GUI runs as the user and cannot signal a process that runs as root.
    Shipping a polkit action for kill would solve that, but such an action lets
    any caller kill any process as root once the prompt is answered, so the
    cancel travels through a pipe instead: the GUI closes its end, the read
    below returns end of file and the writer stops itself at a point where the
    disk is in a consistent state.

    Only a pipe is watched. Started from a terminal stdin is a tty and the read
    would block until the run ends, and redirected from /dev/null it would
    report end of file straight away and cancel a run nobody cancelled.
    """
    try:
        if not stat.S_ISFIFO(os.fstat(0).st_mode):
            return
    except OSError:
        return

    def wait_for_close():
        try:
            while os.read(0, 4096):
                pass
        except OSError:
            pass

        request_stop(signal.SIGTERM)
        if on_cancel is not None:
            on_cancel()

    threading.Thread(target=wait_for_close, daemon=True).start()


def run(cmd, vital=True):
    """Run a command without a shell, aborting if a stop signal arrived.

    A shell is never involved, so a device path or a file name can not turn
    into extra commands. With vital=True a non zero exit raises
    CalledProcessError.
    """
    if stop_requested():
        raise CancelledError()

    subprocess.run(cmd, check=vital)


def sync():
    run(["sync"])


def settle():
    """Wait for udev to catch up with a partition table that just changed.

    parted returns as soon as the kernel accepted the new table, but the device
    node of a partition is created by udev afterwards. Without this wait mkfs
    and mount race against that creation.
    """
    udevadm = shutil.which("udevadm")
    if udevadm is None:
        log("Warning: udevadm command not found.")
        return

    subprocess.run(
        [udevadm, "settle", "--timeout=30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_block_device(path, timeout=15.0):
    """Wait until a partition device node exists. Returns whether it showed up.

    'udevadm settle' already covers the normal case; this is the fallback for
    the systems where udev is slow or not running at all.
    """
    deadline = time.monotonic() + timeout

    while not os.path.exists(path):
        if stop_requested():
            raise CancelledError()
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)

    return True


def exit_as_cancelled():
    """Die by SIGTERM so MainWindow sees a cancellation instead of an error.

    The default handler has to be restored first, otherwise the process would
    only record the stop request again and keep running.
    """
    log("---Writing stopped---")
    sys.stdout.flush()
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGTERM)
    sys.exit(1)  # not reached, the signal above ends the process
