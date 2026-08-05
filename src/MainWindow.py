#!/usr/bin/python3

import os
import signal
import subprocess
import threading
import time
import requests
import hashlib
from collections import deque
from enum import Enum

import gi

gi.require_version("Gtk", "3.0")  # noqa
from gi.repository import Gio, GLib, Gtk, Gdk

import locale
from locale import gettext as _

from USBDeviceManager import connect_usb_refresh_signal, get_usb_devices

# Translation Constants:
APPNAME = "pardus-image-writer"
TRANSLATIONS_PATH = "/usr/share/locale"

# The sums are fetched over TLS: on plain HTTP anyone on the path could hand
# out sums matching a tampered ISO and the check would pass.
MD5SUMS_URL = "https://indir.pardus.org.tr/PARDUS/MD5SUMS"
REQUEST_TIMEOUT_SECONDS = 15

# Speed and remaining time are averaged over this many seconds, otherwise the
# numbers jump around with every single progress line.
SPEED_WINDOW_SECONDS = 5.0

# A burst of progress lines can arrive within milliseconds. Dividing by such a
# short interval produces absurd speeds, so wait until the window is this wide.
MIN_SPEED_SECONDS = 1.0

# Translation functions:
locale.bindtextdomain(APPNAME, TRANSLATIONS_PATH)
locale.textdomain(APPNAME)


def seconds_to_formatted_time(sec):
    """Format a duration as 01:23, growing to 1:02:03 past the hour."""
    hours, remainder = divmod(int(sec), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def seconds_to_unit_time(sec):
    """Format a duration as '1h 23m 45s', leaving out the units that are zero.

    Every unit is a translatable string of its own, so a language can use its
    own abbreviations without the code having to know about them.
    """
    hours, remainder = divmod(int(sec), 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(_("{}h").format(hours))
    if minutes:
        parts.append(_("{}m").format(minutes))
    # Seconds are also shown on their own, e.g. for a duration of exactly 0.
    if seconds or not parts:
        parts.append(_("{}s").format(seconds))

    return " ".join(parts)


class WriteMode(Enum):
    DD = 0
    ISO = 1
    WINDOWS_ISO = 2


class IntegrityResult(Enum):
    OK = 0
    MISMATCH = 1
    NO_CONNECTION = 2
    UNREADABLE = 3


class MainWindow:
    def __init__(self, application, file=""):
        # Set application:
        self.application = application

        # Gtk Builder
        self.builder = Gtk.Builder()

        # Translate things on glade:
        self.builder.set_translation_domain(APPNAME)

        # Import UI file:
        self.builder.add_from_file(
            os.path.dirname(os.path.abspath(__file__)) + "/../ui/MainWindow.glade"
        )
        self.builder.connect_signals(self)

        # Window
        self.define_window()

        # Define UI Components
        self.define_components()

        # Variables
        self.define_variables()

        # USB Manager Initialize
        self.init_usb_manager(file)

        # Update about dialog's version
        self.update_dialog_version()

        # Show Screen:
        self.window.show_all()

    # === WINDOW SETUP ====
    def define_window(self):
        self.window = self.builder.get_object("window")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_application(self.application)
        self.window.connect("destroy", self.on_destroy)

    def define_variables(self):
        self.is_gui_locked = False
        self.second_tick_count = 0
        self.write_mode = WriteMode.DD
        self.image_writer_process_pid = None
        self.image_writer_stdin_fd = None

    def define_components(self):
        def UI(obj):
            return self.builder.get_object(obj)

        self.stack_windows = UI("stack_windows")

        # Main UI
        self.list_devices = UI("list_devices")
        self.cmb_devices = UI("cmb_devices")
        self.btn_select_iso_file = UI("btn_select_iso_file")
        self.lbl_btn_select_iso_file = UI("lbl_btn_select_iso_file")
        self.cmb_modes = UI("cmb_modes")
        self.stack_buttons = UI("stack_buttons")
        self.btn_start = UI("btn_start")
        self.pb_writing_progress = UI("pb_writing_progress")
        self.lbl_writing_details = UI("lbl_writing_details")
        self.stack_write_modes = UI("stack_write_modes")

        # Integrity
        self.cb_checkIntegrity = UI("cb_checkIntegrity")
        self.dialog_integrity = UI("dialog_integrity")
        self.dialog_integrity.set_position(Gtk.WindowPosition.CENTER)
        self.lbl_integrityStatus = UI("lbl_integrityStatus")

        # Dialog:
        self.lbl_prewrite_filename = UI("lbl_prewrite_filename")
        self.lbl_prewrite_disk = UI("lbl_prewrite_disk")
        self.dialog_about = UI("dialog_about")

    def update_dialog_version(self):
        # Set version
        # If can't get from `./__version__` file then accept version in MainWindow.glade file
        with open(
            os.path.dirname(os.path.abspath(__file__)) + "/__version__"
        ) as version_file:
            version = version_file.readline()
            self.dialog_about.set_version(version)

        self.dialog_about.set_program_name(_("Pardus Image Writer"))
        if self.dialog_about.get_titlebar() is None:
            about_headerbar = Gtk.HeaderBar.new()
            about_headerbar.set_show_close_button(True)
            about_headerbar.set_title(_("About Pardus Image Writer"))
            about_headerbar.pack_start(
                Gtk.Image.new_from_icon_name(
                    "pardus-image-writer", Gtk.IconSize.LARGE_TOOLBAR
                )
            )
            about_headerbar.show_all()
            self.dialog_about.set_titlebar(about_headerbar)

    def show_message(self, msg1="", msg2=""):
        dialog = Gtk.MessageDialog(
            self.window,
            0,
            Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK,
            msg1,
        )

        if msg2 != "":
            dialog.format_secondary_text(msg2)

        dialog.run()
        dialog.destroy()

    def lock_gui(self, disableStart=False):
        self.btn_select_iso_file.set_sensitive(False)
        self.cmb_devices.set_sensitive(False)
        self.cb_checkIntegrity.set_sensitive(False)
        self.cmb_modes.set_sensitive(False)

        self.stack_buttons.set_visible_child_name("cancel")
        self.is_gui_locked = True

    def unlock_gui(self):
        self.btn_select_iso_file.set_sensitive(True)
        self.cmb_devices.set_sensitive(True)
        self.cb_checkIntegrity.set_sensitive(True)
        self.cmb_modes.set_sensitive(True)

        self.stack_buttons.set_visible_child_name("start")
        self.is_gui_locked = False

    # === Progress details ===
    def update_writing_details(self, written_bytes, total_bytes):
        """Show the current speed and the remaining time under the bar."""
        now = time.monotonic()
        self.progress_samples.append((now, written_bytes))

        # Drop a sample only while the one behind it still spans the whole
        # window. Pruning any further would collapse the window whenever a
        # burst of lines arrives at once.
        while (
            len(self.progress_samples) > 2
            and now - self.progress_samples[1][0] >= SPEED_WINDOW_SECONDS
        ):
            self.progress_samples.popleft()

        oldest_time, oldest_bytes = self.progress_samples[0]
        elapsed = now - oldest_time

        # Too early to tell: keep whatever is on the label instead of showing a
        # number that is off by orders of magnitude.
        if elapsed < MIN_SPEED_SECONDS:
            return

        speed = (written_bytes - oldest_bytes) / elapsed
        if speed <= 0:
            return

        remaining_seconds = max(total_bytes - written_bytes, 0) / speed
        self.lbl_writing_details.set_label(
            "{:.1f} MB/s   ·   {} {}".format(
                speed / 1000 / 1000,
                _("Remaining"),
                seconds_to_unit_time(remaining_seconds),
            )
        )

    def send_notification(self, title, body):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon(name="pardus-image-writer"))
        notification.set_default_action("app.notification-response::focus")
        self.application.send_notification(
            self.application.get_application_id(), notification
        )

    # === USB Manager ===
    def init_usb_manager(self, iso_file):
        # Get inserted USB devices
        self.iso_file_path = iso_file

        self.usb_device = []
        # The udev observer notifies from its own thread, and Gtk may only be
        # touched from the main loop.
        connect_usb_refresh_signal(lambda: GLib.idle_add(self.list_usb_devices))
        self.list_usb_devices()

        if iso_file:
            self.new_file_selected(iso_file)

    def list_usb_devices(self):
        if self.is_gui_locked:
            return

        deviceList = get_usb_devices()
        self.list_devices.clear()
        for device in deviceList:
            self.list_devices.append(device)

        self.cmb_devices.set_active(0)
        self.stack_buttons.set_visible_child_name("start")

        if len(deviceList) == 0:
            self.btn_start.set_sensitive(False)
        elif self.iso_file_path and not self.is_gui_locked:
            self.btn_start.set_sensitive(True)

    def new_file_selected(self, filepath):
        self.iso_file_path = filepath
        # Case insensitive: PARDUS.ISO is an ISO too.
        iso_file_type = os.path.splitext(filepath)[1].lstrip(".").lower()
        self.lbl_btn_select_iso_file.set_label(os.path.basename(filepath))

        if self.iso_file_path and len(self.usb_device) > 0:
            self.btn_start.set_sensitive(True)

        if iso_file_type != "iso":
            self.cb_checkIntegrity.set_sensitive(False)
            self.stack_write_modes.set_visible_child_name("img_mode")
            self.write_mode = WriteMode.DD
        else:
            self.cb_checkIntegrity.set_sensitive(True)
            self.stack_write_modes.set_visible_child_name("iso_mode")
            self.cmb_modes.set_active(0)

    # == Image Writing ==
    def start_image_writing(self):
        self.written_bytes = 0  # for ISOCopier.py percentage calculation
        self.written_tmp_bytes = 0
        self.total_bytes = 1  # for ISOCopier.py percentage calculation
        self.progress_samples = deque()
        self.lbl_writing_details.set_label("")

        self.lock_gui()
        is_windows = "false"

        script_path = os.path.dirname(os.path.abspath(__file__))

        if self.write_mode == WriteMode.DD:
            script_path += "/ImageWriter.py"
        elif self.write_mode == WriteMode.ISO:
            script_path += "/ISOCopier.py"
        elif self.write_mode == WriteMode.WINDOWS_ISO:
            script_path += "/ISOCopier.py"
            is_windows = "true"

        self.spawn_process(
            [
                "pkexec",
                script_path,
                self.iso_file_path,
                "/dev/" + self.usb_device[0],
                is_windows,
            ]
        )
        self.pb_writing_progress.set_text(_("Creating partitions..."))

    def prepare_image_writing(self):
        if not self.cb_checkIntegrity.get_active():
            self.start_image_writing()
            return

        self.lock_gui(disableStart=True)
        self.dialog_integrity.show_all()

        # Downloading the sums and hashing a multi gigabyte ISO both block for
        # a long time, so they run off the GTK main loop.
        threading.Thread(target=self.check_md5, daemon=True).start()

    def check_md5(self):
        """Worker thread: never touch a Gtk widget from here, only idle_add."""
        try:
            response = requests.get(MD5SUMS_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            md5sums = response.text
        except requests.RequestException:
            GLib.idle_add(self.on_integrity_checked, IntegrityResult.NO_CONNECTION)
            return

        try:
            md5sum_of_iso = self.calculate_md5_of_file(self.iso_file_path)
        except OSError:
            GLib.idle_add(self.on_integrity_checked, IntegrityResult.UNREADABLE)
            return

        # Compare against the hash column instead of searching the whole file,
        # so a hash can only match where a hash is expected.
        matched = any(
            line.split()[:1] == [md5sum_of_iso] for line in md5sums.splitlines()
        )

        GLib.idle_add(
            self.on_integrity_checked,
            IntegrityResult.OK if matched else IntegrityResult.MISMATCH,
        )

    def on_integrity_checked(self, result):
        """Back on the main thread with the outcome of the integrity check."""
        self.dialog_integrity.hide()

        if result is IntegrityResult.OK:
            self.start_image_writing()
            return False

        self.unlock_gui()

        if result is IntegrityResult.NO_CONNECTION:
            detail = _("Could not connect to pardus.org.tr.")
        elif result is IntegrityResult.UNREADABLE:
            detail = _("The file could not be read.")
        else:
            detail = _("This is not a Pardus ISO, or it is corrupted.")

        self.show_message(_("Integrity checking failed."), detail)

        return False

    def spawn_process(self, params):
        # No LEAVE_DESCRIPTORS_OPEN: the privileged child has no business
        # inheriting the file descriptors of this process.
        #
        # The pipe on stdin is how the run is cancelled. This process runs as
        # the user and cannot signal a child that runs as root, and the polkit
        # action for kill that used to bridge that gap granted far more than
        # stopping this one process: it ran kill as root with whatever
        # arguments the caller passed.
        (
            self.image_writer_process_pid,
            self.image_writer_stdin_fd,
            stdout,
            _stderr,
        ) = GLib.spawn_async(
            params,
            flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_DO_NOT_REAP_CHILD,
            standard_input=True,
            standard_output=True,
            standard_error=False,
        )

        GLib.io_add_watch(
            GLib.IOChannel(stdout), GLib.IO_IN | GLib.IO_HUP, self.on_process_stdout
        )

        GLib.child_watch_add(
            GLib.PRIORITY_DEFAULT, self.image_writer_process_pid, self.on_process_exit
        )

    def close_writer_stdin(self):
        """Close the pipe the writer reads, which is both the cancel and the
        cleanup. Safe to call twice."""
        if self.image_writer_stdin_fd is None:
            return

        try:
            os.close(self.image_writer_stdin_fd)
        except OSError:
            pass

        self.image_writer_stdin_fd = None

    def cancel_image_writing(self):
        # Closing the pipe is the cancel: the writer reaches the end of its
        # stdin and stops itself at a point where the disk is consistent. There
        # is no pid involved any more, so a recycled pid cannot be signalled.
        self.close_writer_stdin()

    def start_interval_tick(self):
        GLib.timeout_add(1000, self.on_interval_tick)

    def stop_interval_tick(self):
        self.stop_interval_tick_flag = True

    def calculate_md5_of_file(self, filename):
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    # === SIGNALS ===
    # Button Signals:
    def on_btn_select_iso_file_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            _("Select ISO or IMG File"),
            action=Gtk.FileChooserAction.OPEN,
            buttons=(
                Gtk.STOCK_CANCEL,
                Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN,
                Gtk.ResponseType.OK,
            ),
        )

        file_filter = Gtk.FileFilter()
        file_filter.set_name("*.iso, *.img")
        file_filter.add_pattern("*.iso")
        file_filter.add_pattern("*.img")
        dialog.add_filter(file_filter)

        dialog.show()
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        filepath = dialog.get_filename()

        self.new_file_selected(filepath)

        dialog.destroy()

    def on_btn_start_clicked(self, button):
        # Ask if it is ok?
        self.lbl_prewrite_filename.set_markup(
            "- <b>{}</b>".format(self.iso_file_path.split("/")[-1])
        )
        self.lbl_prewrite_disk.set_markup(
            "- <b>{} [ {} ]</b> <i>( /dev/{} )</i>".format(
                self.usb_device[1], self.usb_device[2], self.usb_device[0]
            )
        )

        self.stack_windows.set_visible_child_name("prewrite")

    def on_btn_cancel_clicked(self, button):
        self.cancel_image_writing()

    def on_btn_exit_clicked(self, button):
        self.window.get_application().quit()

    def on_btn_write_new_file_clicked(self, button):
        self.pb_writing_progress.set_text()
        self.pb_writing_progress.set_fraction(0)
        self.lbl_writing_details.set_label("")
        self.stack_windows.set_visible_child_name("main")

    def on_btn_information_clicked(self, button):
        self.dialog_about.run()
        self.dialog_about.hide()

    def on_btn_prewrite_yes_clicked(self, button):
        self.second_tick_count = 0
        self.copying_finished = False
        self.stack_windows.set_visible_child_name("main")
        GLib.idle_add(self.prepare_image_writing)

    def on_btn_prewrite_cancel_clicked(self, button):
        self.stack_windows.set_visible_child_name("main")

    # Combobox Signals
    def on_cmb_devices_changed(self, combobox):
        tree_iter = combobox.get_active_iter()
        if tree_iter:
            model = combobox.get_model()
            device_info = model[tree_iter][:3]
            self.usb_device = device_info
        else:
            self.btn_start.set_sensitive(False)

    def on_cmb_modes_changed(self, combobox):
        tree_iter = combobox.get_active_iter()

        if not tree_iter:
            return

        model = combobox.get_model()
        self.write_mode = WriteMode(model[tree_iter][0])  # 0:DD, 1:Iso, 2:Win ISO

        # ISO Mode grub packages control
        if self.write_mode == WriteMode.ISO or self.write_mode == WriteMode.WINDOWS_ISO:
            if not os.path.isdir("/usr/lib/grub/i386-pc") or not os.path.isdir(
                "/usr/lib/grub/x86_64-efi"
            ):
                if os.path.isfile("/usr/bin/pardus-software"):
                    dialog = Gtk.MessageDialog(
                        self.window,
                        0,
                        Gtk.MessageType.ERROR,
                        Gtk.ButtonsType.OK_CANCEL,
                        _("Grub packages needed for ISO Mode."),
                    )

                    dialog.format_secondary_text(
                        _("Would you like to install it from Pardus Software Center?")
                    )

                    response = dialog.run()
                    if response == Gtk.ResponseType.OK:
                        subprocess.run(
                            [
                                "pardus-software",
                                "--details",
                                "pardus-image-writer-grub-tools",
                            ]
                        )

                    dialog.destroy()
                else:
                    self.show_message(
                        _("Grub packages needed for ISO Mode."),
                        _(
                            "Please install 'grub-efi-amd64-bin' and 'grub-pc-bin' packages."
                        ),
                    )

                combobox.set_active(0)  # revert to DD mode

    # Process Signals
    def on_process_stdout(self, source, condition):
        # condition is a bit mask, IO_IN and IO_HUP can arrive together.
        if condition & GLib.IO_HUP:
            return False

        line = source.readline().strip()

        if self.write_mode == WriteMode.DD:
            # A malformed or empty line must not take down the io watch.
            fields = line.split()
            if len(fields) != 2 or not all(field.isdigit() for field in fields):
                return True

            written = int(fields[0])
            total = int(fields[1])
            percent = 0
            if total > 0:
                percent = written / total

            self.pb_writing_progress.set_text(
                "{}MB / {}MB (%{:.1f})".format(
                    round(written / 1000 / 1000),
                    round(total / 1000 / 1000),
                    int(percent * 1000) / 10,
                )
            )
            self.pb_writing_progress.set_fraction(percent)
            self.update_writing_details(written, total)
        else:
            # Every field is validated before it is used: an unparsable line
            # would raise out of the io watch and the watch would be dropped,
            # so the rest of the write would report no progress at all.
            if line.startswith("COPIED:"):  # COPIED:10:20
                fields = line.split(":")
                if len(fields) != 3 or not all(f.isdigit() for f in fields[1:]):
                    return True

                self.written_bytes += self.written_tmp_bytes
                self.written_tmp_bytes = 0
                if int(fields[1]) == int(fields[2]):
                    self.copying_finished = True

            elif line.startswith("BYTES:"):  # BYTES:1234756
                value = line[len("BYTES:") :]
                if not value.isdigit():
                    return True
                self.written_tmp_bytes = int(value)

            elif line.startswith("TOTAL_BYTES:"):  # TOTAL_BYTES:1234756
                value = line[len("TOTAL_BYTES:") :]
                if not value.isdigit():
                    return True
                # An empty ISO is rejected by the writer, but a zero here would
                # still divide below.
                self.total_bytes = max(int(value), 1)
                self.start_interval_tick()

            else:
                return True

            percent = (self.written_bytes + self.written_tmp_bytes) / self.total_bytes
            elapsed_time = seconds_to_formatted_time(self.second_tick_count)

            # print(f"{self.written_bytes + self.written_tmp_bytes} / {self.total_bytes}")

            if self.copying_finished:
                self.pb_writing_progress.set_text(_("Installing GRUB..."))
                self.lbl_writing_details.set_label("")
            elif self.total_bytes > 1:
                self.pb_writing_progress.set_text(
                    "{} | %{:.1f}".format(elapsed_time, int(percent * 1000) / 10)
                )
                self.pb_writing_progress.set_fraction(percent)
                self.update_writing_details(
                    self.written_bytes + self.written_tmp_bytes, self.total_bytes
                )
            else:
                self.pb_writing_progress.set_text(_("Creating partitions..."))

        return True

    def on_process_exit(self, pid, status):
        # DO_NOT_REAP_CHILD means the pid stays allocated until it is closed.
        GLib.spawn_close_pid(pid)
        self.image_writer_process_pid = None
        self.close_writer_stdin()

        self.unlock_gui()
        self.list_usb_devices()
        self.pb_writing_progress.set_fraction(1)
        self.lbl_writing_details.set_label("")

        # status is a raw wait status, not an exit code.
        if os.WIFSIGNALED(status):
            exit_code = -os.WTERMSIG(status)
        elif os.WIFEXITED(status):
            exit_code = os.WEXITSTATUS(status)
        else:
            exit_code = status

        # Killed by SIGTERM means the user cancelled; pkexec answers 126 when
        # the authentication dialog is dismissed and 127 when it cannot run.
        cancelled_or_unauthorized = exit_code in (-signal.SIGTERM, 126, 127)

        if exit_code == 0:
            self.send_notification(
                _("Writing process is finished."),
                os.path.basename(self.iso_file_path)
                + " | "
                + _("You can eject the USB disk."),
            )
            self.pb_writing_progress.set_text(_("Finished"))
            self.stack_windows.set_visible_child_name("finished")
        elif not cancelled_or_unauthorized:
            self.pb_writing_progress.set_text(_("Error!"))
            self.pb_writing_progress.set_fraction(0)

            self.show_message(
                _("An error occured while writing the file to the disk."),
                _(
                    "Please make sure the USB device is connected properly and try again."
                ),
            )
        else:
            self.pb_writing_progress.set_text()
            self.pb_writing_progress.set_fraction(0)

    # Elapsed Time Interval Tick
    def on_interval_tick(self):
        self.second_tick_count += 1

        if not self.is_gui_locked or self.copying_finished:
            return False

        percent = self.pb_writing_progress.get_fraction()
        elapsed_time = seconds_to_formatted_time(self.second_tick_count)

        if self.write_mode != WriteMode.DD:
            self.pb_writing_progress.set_text(
                "{} | %{:.1f}".format(elapsed_time, int(percent * 1000) / 10)
            )
        else:
            return False

        return True

    # Window
    def on_destroy(self, action):
        self.window.get_application().quit()
