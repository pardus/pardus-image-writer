#!/usr/bin/python3

import os
import subprocess
import requests
import hashlib
import threading

import gi

gi.require_version("Gtk", "3.0")  # noqa
from gi.repository import Gio, GLib, Gtk, Gdk

import locale
from locale import gettext as _

from USBDeviceManager import USBDeviceManager

# Translation Constants:
APPNAME = "pardus-image-writer"
TRANSLATIONS_PATH = "/usr/share/locale"

# Translation functions:
locale.bindtextdomain(APPNAME, TRANSLATIONS_PATH)
locale.textdomain(APPNAME)


def seconds_to_formatted_time(sec):
    minutes, seconds = divmod(sec, 60)
    return f"{minutes:02d}:{seconds:02d}"


class MainWindow:
    def __init__(self, application, file=""):
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
        self.window = self.builder.get_object("window")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_application(application)
        self.window.connect("destroy", self.on_destroy)
        self.define_components()

        # Variables
        self.define_variables()

        self.init_usb_manager(file)

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

        # Set application:
        self.application = application

        # Show Screen:
        self.window.show_all()

    # Window methods:
    def on_destroy(self, action):
        self.window.get_application().quit()

    def define_variables(self):
        # Variables
        self.is_gui_locked = False
        self.second_tick_count = 0
        # ImageWriter.py for DD Mode, ISOCopier.py for ISO Mode
        self.write_mode = "ImageWriter.py"

    def init_usb_manager(self, file):
        # Get inserted USB devices
        self.iso_file_path = file
        if file:
            self.new_file_selected(file)

        self.usb_device = []
        self.usb_manager = USBDeviceManager()
        self.usb_manager.connect_usb_refresh_signal(self.list_usb_devices)
        self.list_usb_devices()

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

    # USB Methods
    def list_usb_devices(self):
        if self.is_gui_locked:
            return

        deviceList = self.usb_manager.get_usb_devices()
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
        iso_file_type = filepath.split(".")[-1]
        self.lbl_btn_select_iso_file.set_label(filepath.split("/")[-1])

        if self.iso_file_path and len(self.usb_device) > 0:
            self.btn_start.set_sensitive(True)

        if iso_file_type != "iso":
            self.cb_checkIntegrity.set_sensitive(False)
            self.stack_write_modes.set_visible_child_name("img_mode")
            self.write_mode = "ImageWriter.py"
        else:
            self.cb_checkIntegrity.set_sensitive(True)
            self.stack_write_modes.set_visible_child_name("iso_mode")
            self.cmb_modes.set_active(0)

    def btn_selectISOFile_clicked(self, button):
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

    def cmb_devices_changed(self, combobox):
        tree_iter = combobox.get_active_iter()
        if tree_iter:
            model = combobox.get_model()
            device_info = model[tree_iter][:3]
            self.usb_device = device_info
        else:
            self.btn_start.set_sensitive(False)

    def cmb_modes_changed(self, combobox):
        tree_iter = combobox.get_active_iter()

        if not tree_iter:
            return

        model = combobox.get_model()
        self.write_mode = model[tree_iter][0]  # 0:DD, 1:Iso, 2:Win ISO
        if self.write_mode == 0:
            self.write_mode = "ImageWriter.py"
        elif self.write_mode == 1:
            self.write_mode = "ISOCopier.py"
        elif self.write_mode == 2:
            self.write_mode = "WinUSB.py"

    # Buttons:
    def btn_start_clicked(self, button):
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

    def btn_cancel_clicked(self, button):
        self.cancel_image_writing()

    def btn_exit_clicked(self, button):
        self.window.get_application().quit()

    def btn_write_new_file_clicked(self, button):
        self.stack_windows.set_visible_child_name("main")

    def btn_information_clicked(self, button):
        self.dialog_about.run()
        self.dialog_about.hide()

    def btn_prewrite_yes_clicked(self, button):
        self.second_tick_count = 0
        self.copying_finished = False
        self.stack_windows.set_visible_child_name("main")
        GLib.idle_add(self.prepare_image_writing)

    def btn_prewrite_cancel_clicked(self, button):
        self.stack_windows.set_visible_child_name("main")

    def show_message(self, msg1="", msg2=""):
        dialog = Gtk.MessageDialog(
            self.window,
            0,
            Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK,
            _(msg1),
        )
        dialog.format_secondary_text(_(msg2))
        dialog.run()
        dialog.destroy()

    def start_image_writing(self):
        self.written_bytes = 0  # for ISOCopier.py percentage calculation
        self.written_tmp_bytes = 0
        self.total_bytes = 1  # for ISOCopier.py percentage calculation

        self.lock_gui()
        self.spawn_process(
            [
                "pkexec",
                os.path.dirname(os.path.abspath(__file__)) + "/" + self.write_mode,
                self.iso_file_path,
                "/dev/" + self.usb_device[0],
            ]
        )
        self.pb_writing_progress.set_text("Creating partitions...")

    def start_interval_tick(self):
        GLib.timeout_add(1000, self.on_interval_tick)

    def stop_interval_tick(self):
        self.stop_interval_tick_flag = True

    def prepare_image_writing(self):
        if not self.cb_checkIntegrity.get_active():
            self.start_image_writing()
            return

        self.lock_gui(disableStart=True)
        self.dialog_integrity.show_all()

        # Get MD5SUMS Request
        try:
            result = requests.get(
                "http://indir.pardus.org.tr/PARDUS/MD5SUMS"
            )  # blocking
            md5sums = result.text

            md5sum_of_iso = self.calculate_md5_of_file(self.iso_file_path)
            if md5sum_of_iso in md5sums:
                self.start_image_writing()
                self.dialog_integrity.hide()
            else:
                self.dialog_integrity.hide()
                self.unlock_gui()
                dialog = Gtk.MessageDialog(
                    self.window,
                    0,
                    Gtk.MessageType.ERROR,
                    Gtk.ButtonsType.OK,
                    _("Integrity checking failed."),
                )
                dialog.format_secondary_text(
                    _("This is not a Pardus ISO, or it is corrupted.")
                )
                dialog.run()
                dialog.destroy()
        except requests.ConnectionError:
            self.dialog_integrity.hide()
            self.unlock_gui()
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                _("Integrity checking failed."),
            )
            dialog.format_secondary_text(_("Could not connect to pardus.org.tr."))
            dialog.run()
            dialog.destroy()

    def cancel_image_writing(self):
        subprocess.call(
            ["pkexec", "kill", "-SIGTERM", str(self.image_writer_process_pid)]
        )

    def spawn_process(self, params):
        self.image_writer_process_pid, _, stdout, _ = GLib.spawn_async(
            params,
            flags=GLib.SPAWN_SEARCH_PATH
            | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN
            | GLib.SPAWN_DO_NOT_REAP_CHILD,
            standard_input=False,
            standard_output=True,
            standard_error=False,
        )

        GLib.io_add_watch(
            GLib.IOChannel(stdout), GLib.IO_IN | GLib.IO_HUP, self.on_process_stdout
        )

        GLib.child_watch_add(
            GLib.PRIORITY_DEFAULT, self.image_writer_process_pid, self.on_process_exit
        )

    def on_process_stdout(self, source, condition):
        if condition == GLib.IO_HUP:
            return False

        line = source.readline().strip()

        if self.write_mode == "ImageWriter.py":
            written, total = line.split()
            written = int(written)
            total = int(total)
            percent = 0
            if total > 0:
                percent = written / total

            # debug
            # print("imagewriter.py> " + line)

            self.pb_writing_progress.set_text(
                "{}MB / {}MB (%{:.1f})".format(
                    round(written / 1000 / 1000),
                    round(total / 1000 / 1000),
                    int(percent * 1000) / 10,
                )
            )
            self.pb_writing_progress.set_fraction(percent)
        elif self.write_mode == "ISOCopier.py":
            # print("isocopier.py> '{}'".format(line))

            if line[0:7] == "COPIED:":  # COPIED:10:20
                self.written_bytes += self.written_tmp_bytes
                self.written_tmp_bytes = 0
                values = line.split(":")
                if int(values[1]) == int(values[2]):
                    self.copying_finished = True
                    self.pb_writing_progress.set_text("Installing GRUB...")

            elif line[0:6] == "BYTES:":  # BYTES:1234756
                self.written_tmp_bytes = int(line.split(":")[-1])
            elif line[0:12] == "TOTAL_BYTES:":  # TOTAL_BYTES:1234756
                self.total_bytes = int(line.split(":")[-1])
                self.start_interval_tick()

            percent = (self.written_bytes + self.written_tmp_bytes) / self.total_bytes
            elapsed_time = seconds_to_formatted_time(self.second_tick_count)

            # print(f"{self.written_bytes + self.written_tmp_bytes} / {self.total_bytes}")

            if self.copying_finished:
                self.pb_writing_progress.set_text(_("Installing GRUB..."))
            elif self.total_bytes > 1:
                self.pb_writing_progress.set_text(
                    "{} | %{:.1f}".format(elapsed_time, int(percent * 1000) / 10)
                )
                self.pb_writing_progress.set_fraction(percent)
            else:
                self.pb_writing_progress.set_text(_("Creating partitions..."))

        return True

    def on_process_exit(self, pid, status):
        self.unlock_gui()
        self.list_usb_devices()
        self.pb_writing_progress.set_fraction(1)

        if status == 0:
            # self.pb_writingProgess.set_text("0%")
            self.send_notification(
                _("Writing process is finished."), _("You can eject the USB disk.")
            )
            self.pb_writing_progress.set_text(_("Finished"))
            self.stack_windows.set_visible_child_name("finished")
        elif status != 15 and status != 32256:  # these are cancelling or auth error.
            self.pb_writing_progress.set_text(_("Error!"))
            self.pb_writing_progress.set_fraction(0)
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                _("An error occured while writing the file to the disk."),
            )
            dialog.format_secondary_text(
                _(
                    "Please make sure the USB device is connected properly and try again."
                )
            )
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

    def send_notification(self, title, body):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon(name="pardus-image-writer"))
        notification.set_default_action("app.notification-response::focus")
        self.application.send_notification(
            self.application.get_application_id(), notification
        )

    def calculate_md5_of_file(self, filename):
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def on_interval_tick(self):
        self.second_tick_count += 1

        if not self.is_gui_locked or self.copying_finished:
            return False

        percent = self.pb_writing_progress.get_fraction()
        elapsed_time = seconds_to_formatted_time(self.second_tick_count)

        if self.write_mode != "ImageWriter.py":
            self.pb_writing_progress.set_text(
                "{} | %{:.1f}".format(elapsed_time, int(percent * 1000) / 10)
            )
        else:
            return False

        return True
