import os
import subprocess
import sys

import gi
import requests

gi.require_version('Gtk', '3.0')
import locale
from locale import gettext as tr

from gi.repository import Gio, GLib, Gtk

from USBDeviceManager import USBDeviceManager

# Translation Constants:
APPNAME = "pardus-image-writer"
TRANSLATIONS_PATH = "/usr/share/locale"
SYSTEM_LANGUAGE = os.environ.get("LANG")

# Translation functions:
locale.bindtextdomain(APPNAME, TRANSLATIONS_PATH)
locale.textdomain(APPNAME)
locale.setlocale(locale.LC_ALL, SYSTEM_LANGUAGE)


class MainWindow:
    def __init__(self, application, file=""):
        # Gtk Builder
        self.builder = Gtk.Builder()

        # Translate things on glade:
        self.builder.set_translation_domain(APPNAME)

        # Import UI file:
        self.builder.add_from_file(os.path.dirname(os.path.abspath(__file__)) + "/../ui/MainWindow.glade")
        self.builder.connect_signals(self)

        # Window
        self.window = self.builder.get_object("window")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_application(application)
        self.window.connect("destroy", self.onDestroy)
        self.defineComponents()

        # Variables
        self.isGUILocked = False
        self.writeMode = "ImageWriter.py"  # ImageWriter.py for DD Mode, ISOCopier.py for ISO Mode

        # Get inserted USB devices
        self.imgFilepath = file
        if file:
            self.lbl_btn_selectISOFile.set_label(file.split('/')[-1])

        self.usbDevice = []
        self.usbManager = USBDeviceManager()
        self.usbManager.setUSBRefreshSignal(self.listUSBDevices)
        self.listUSBDevices()

        # Set version
        # If not getted from __version__ file then accept version in MainWindow.glade file
        try:
            version = open(os.path.dirname(os.path.abspath(__file__)) + "/__version__").readline()
            self.dialog_about.set_version(version)
        except:
            pass

        self.dialog_about.set_program_name(tr("Pardus Image Writer"))

        # Set application:
        self.application = application

        # Show Screen:
        self.window.show_all()

        # Debian based only signals
        if self.isdebian():
            self.installation_window()

    # Window methods:
    def onDestroy(self, action):
        self.window.get_application().quit()

    def defineComponents(self):
        self.stack_windows = self.builder.get_object("stack_windows")

        self.list_devices = self.builder.get_object("list_devices")
        self.cmb_devices = self.builder.get_object("cmb_devices")
        self.btn_selectISOFile = self.builder.get_object("btn_selectISOFile")
        self.lbl_btn_selectISOFile = self.builder.get_object("lbl_btn_selectISOFile")
        self.cmb_modes = self.builder.get_object("cmb_modes")
        self.stack_buttons = self.builder.get_object("stack_buttons")
        self.btn_start = self.builder.get_object("btn_start")
        self.pb_writingProgess = self.builder.get_object("pb_writingProgress")

        # Integrity
        self.cb_checkIntegrity = self.builder.get_object("cb_checkIntegrity")
        self.dialog_integrity = self.builder.get_object("dialog_integrity")
        self.dialog_integrity.set_position(Gtk.WindowPosition.CENTER)
        self.lbl_integrityStatus = self.builder.get_object("lbl_integrityStatus")

        # Dialog:
        self.dialog_write = self.builder.get_object("dialog_write")
        self.dialog_write.set_position(Gtk.WindowPosition.CENTER)
        self.dlg_lbl_filename = self.builder.get_object("dlg_lbl_filename")
        self.dlg_lbl_disk = self.builder.get_object("dlg_lbl_disk")
        self.dialog_about = self.builder.get_object("dialog_about")

    # USB Methods
    def listUSBDevices(self):
        if self.isGUILocked == True:
            return

        deviceList = self.usbManager.getUSBDevices()
        self.list_devices.clear()
        for device in deviceList:
            self.list_devices.append(device)

        self.cmb_devices.set_active(0)
        self.stack_buttons.set_visible_child_name("start")

        if len(deviceList) == 0:
            self.btn_start.set_sensitive(False)
        elif self.imgFilepath and self.isGUILocked == False:
            self.btn_start.set_sensitive(True)

    def btn_selectISOFile_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            tr("Select ISO File..."),
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )

        fileFilter = Gtk.FileFilter()
        fileFilter.set_name("*.iso, *.img")
        fileFilter.add_pattern("*.iso")
        fileFilter.add_pattern("*.img")
        dialog.add_filter(fileFilter)

        dialog.show()
        response = dialog.run()
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        filepath = dialog.get_filename()

        self.imgFilepath = filepath
        self.lbl_btn_selectISOFile.set_label(filepath.split('/')[-1])
        self.fileType = filepath.split(".")[-1]

        if self.imgFilepath and len(self.usbDevice) > 0:
            self.btn_start.set_sensitive(True)

        dialog.destroy()


    def cmb_devices_changed(self, combobox):
        tree_iter = combobox.get_active_iter()
        if tree_iter:
            model = combobox.get_model()
            deviceInfo = model[tree_iter][:3]
            self.usbDevice = deviceInfo
        else:
            self.btn_start.set_sensitive(False)

    def cmb_modes_changed(self, combobox):
        tree_iter = combobox.get_active_iter()

        if not tree_iter:
            return

        model = combobox.get_model()
        self.writeMode = model[tree_iter][0]  # 0:DD, 1:Iso
        if self.writeMode == 0:
            self.writeMode = "ImageWriter.py"
            return
        elif self.writeMode == 1:
            self.writeMode = "ISOCopier.py"
        elif self.writeMode == 2:
            self.writeMode = "WinUSB.py"

        if not os.path.isdir("/usr/lib/grub/i386-pc"):
            combobox.set_active(0)
            self.writeMode = 0
            if not self.isdebian():
                self.show_message(tr("Target {} does not exists").format("i386-pc"),
                                  tr("Please install {}").format("grub-pc-bin"))
            else:
                self.builder.get_object("mode_installer").set_current_page(1)
            self.builder.get_object("mode_label").set_text(tr("{} not found").format("grub-i386-pc"))
        elif not os.path.isdir("/usr/lib/grub/x86_64-efi"):
            combobox.set_active(0)
            self.writeMode = 0
            if not self.isdebian():
                self.show_message(tr("Target {} does not exists").format("x86_64-efi"),
                                  tr("Please install {}").format("grub-efi-amd64-bin"))
            else:
                self.builder.get_object("mode_installer").set_current_page(1)
            self.builder.get_object("mode_label").set_text(tr("{} not found").format("grub-x86_64-amd64-efi"))

    # Buttons:
    def btn_start_clicked(self, button):
        self.prepareWriting()

    def btn_cancel_clicked(self, button):
        self.cancelWriting()

    def btn_exit_clicked(self, button):
        self.window.get_application().quit()

    def btn_write_new_file_clicked(self, button):
        self.stack_windows.set_visible_child_name("main")

    def btn_information_clicked(self, button):
        self.dialog_about.run()
        self.dialog_about.hide()

    def show_message(self, msg1="", msg2=""):
        dialog = Gtk.MessageDialog(
            self.window,
            0,
            Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK,
            tr(msg1),
        )
        dialog.format_secondary_text(
            tr(msg2)
        )
        dialog.run()
        dialog.destroy()

    def isdebian(self):
        return os.path.exists("/var/lib/dpkg/status")

    def installation_window(self):
        yes = self.builder.get_object("but_inst")
        no = self.builder.get_object("but_canc")
        nm = self.builder.get_object("mode_installer")
        nm.set_current_page(0)

        def yes_event(widget):
            nm.set_current_page(2)
            apt_install_grub()

        def no_event(widget):
            nm.set_current_page(0)

        def apt_install_grub():
            params = "pkexec apt install --reinstall grub-pc-bin grub-efi-amd64-bin -yq".split(" ")

            def onProcessExit(pid, status):
                if status == 0:
                    self.builder.get_object("mod_message").set_text(tr("Installation done."))
                else:
                    self.builder.get_object("mod_message").set_text(tr("Installation failed."))
                nm.set_current_page(3)
                yes.set_sensitive(True)

            try:
                writerProcessPID, _, stdout, _ = GLib.spawn_async(params,
                                                                  flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN | GLib.SPAWN_DO_NOT_REAP_CHILD,
                                                                  standard_input=False, standard_output=True,
                                                                  standard_error=False)
            except:
                nm.set_current_page(3)
                self.builder.get_object("mod_message").set_text(tr("Installation failed."))
            GLib.child_watch_add(GLib.PRIORITY_DEFAULT, writerProcessPID, onProcessExit)

        yes.connect("clicked", yes_event)
        no.connect("clicked", no_event)
        self.builder.get_object("go_back").connect("clicked", no_event)

    def onCheckingIntegrityFinished(self):
        # Check ISO has checksum on list:
        isISOGood = False
        for line in self.checksumlist:
            if line.strip() and line.split()[0] == self.checksum_of_file.split()[0]:
                isISOGood = True
                break

        if isISOGood:
            self.startWriting()
        else:
            self.unlockGUI()
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                tr("Integrity checking failed."),
            )
            dialog.format_secondary_text(
                tr("This is not a Pardus ISO, or it is corrupted.")
            )
            dialog.run()
            dialog.destroy()

        self.dialog_integrity.hide()

    def startWriting(self):
        self.lockGUI()
        self.startProcess([
            "pkexec",
            os.path.dirname(os.path.abspath(__file__)) + "/" + self.writeMode,
            self.imgFilepath,
            '/dev/' + self.usbDevice[0],
        ])

    def prepareWriting(self):
        # Ask if it is ok?
        self.dlg_lbl_filename.set_markup("- <b>{}</b>".format(self.imgFilepath.split('/')[-1]))
        self.dlg_lbl_disk.set_markup(
            "- <b>{} [ {} ]</b> <i>( /dev/{} )</i>".format(self.usbDevice[1], self.usbDevice[2], self.usbDevice[0]))

        response = self.dialog_write.run()
        self.dialog_write.hide()

        if response != Gtk.ResponseType.YES:
            return

        if not self.cb_checkIntegrity.get_active():
            self.startWriting()
            return

        self.lockGUI(disableStart=True)
        self.dialog_integrity.show_all()
        self.finishedProcesses = 0

        self.checksumlist = []
        self.check_of_file = ""

        # Check checksum value of the ISO file:
        def on_checksum_stdout(source, condition):
            if condition == GLib.IO_HUP:
                return False

            self.checksum_of_file = source.readline().strip()
            return True

        def on_checksum_finished(pid, status):
            self.finishedProcesses += 1
            if self.finishedProcesses == 2:
                self.onCheckingIntegrityFinished()

        if requests.head("http://indir.pardus.org.tr/PARDUS/SHA512SUMS").status_code == 200:
            checksum_command = "sha512sum"
            checksums_url = "http://indir.pardus.org.tr/PARDUS/SHA512SUMS"
        else:
            checksum_command = "md5sum"
            checksums_url = "http://indir.pardus.org.tr/PARDUS/MD5SUMS"

        checksum_pid, _, checksum_stdout, _ = GLib.spawn_async([checksum_command, self.imgFilepath],
                                                     flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN | GLib.SPAWN_DO_NOT_REAP_CHILD,
                                                     standard_input=False, standard_output=True,
                                                     standard_error=False)
        GLib.io_add_watch(GLib.IOChannel(checksum_stdout), GLib.IO_IN | GLib.IO_HUP, on_checksum_stdout)
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT, checksum_pid, on_checksum_finished)

        # Get checksums from pardus.org.tr:
        try:
            result = requests.get(checksums_url)
            self.checksumlist = result.text.splitlines()
            on_checksum_finished(0, 0)
        except requests.ConnectionError:
            self.dialog_integrity.hide()
            self.unlockGUI()
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                tr("Integrity checking failed."),
            )
            dialog.format_secondary_text(
                tr("Could not connect to pardus.org.tr.")
            )
            dialog.run()
            dialog.destroy()

    def cancelWriting(self):
        subprocess.call(["pkexec", "kill", "-SIGTERM", str(self.writerProcessPID)])

    def startProcess(self, params):
        self.writerProcessPID, _, stdout, _ = GLib.spawn_async(params,
                                                               flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN | GLib.SPAWN_DO_NOT_REAP_CHILD,
                                                               standard_input=False, standard_output=True,
                                                               standard_error=False)

        GLib.io_add_watch(GLib.IOChannel(stdout), GLib.IO_IN | GLib.IO_HUP, self.onProcessStdout)

        GLib.child_watch_add(GLib.PRIORITY_DEFAULT, self.writerProcessPID, self.onProcessExit)

    def onProcessStdout(self, source, condition):
        if condition == GLib.IO_HUP:
            return False

        line = source.readline().strip()

        if self.writeMode == "ImageWriter.py":
            written, total = line.split()
            written = int(written)
            total = int(total)
            percent = 0
            if total > 0:
                percent = written / total

            self.pb_writingProgess.set_text(
                "{}MB / {}MB (%{})".format(round(written / 1000 / 1000), round(total / 1000 / 1000),
                                           int(percent * 100)))
            self.pb_writingProgess.set_fraction(percent)
        else:
            if line[0:9] == "PROGRESS:":
                _, copied, total = line.split(":")
                copied = int(copied)
                total = int(total)

                percent = 0
                if total > 0:
                    percent = copied / total

                self.pb_writingProgess.set_text("%{}".format(int(percent * 100)))
                self.pb_writingProgess.set_fraction(percent)
        return True

    def onProcessExit(self, pid, status):
        self.unlockGUI()
        self.listUSBDevices()
        self.pb_writingProgess.set_fraction(0)

        if status == 0:
            self.pb_writingProgess.set_text("0%")
            self.sendNotification(tr("Writing process is finished."), tr("You can eject the USB disk."))
            self.stack_windows.set_visible_child_name("finished")
        elif status != 15 and status != 32256:  # these are cancelling or auth error.
            self.pb_writingProgess.set_text(tr("Error!"))
            self.pb_writingProgess.set_fraction(0)
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                tr("An error occured while writing the file to the disk."),
            )
            dialog.format_secondary_text(
                tr("Please make sure the USB device is connected properly and try again.")
            )
            dialog.run()
            dialog.destroy()

    def lockGUI(self, disableStart=False):
        self.btn_selectISOFile.set_sensitive(False)
        self.cmb_devices.set_sensitive(False)
        self.cb_checkIntegrity.set_sensitive(False)
        self.cmb_modes.set_sensitive(False)

        self.stack_buttons.set_visible_child_name("cancel")
        self.isGUILocked = True

    def unlockGUI(self):
        self.btn_selectISOFile.set_sensitive(True)
        self.cmb_devices.set_sensitive(True)
        self.cb_checkIntegrity.set_sensitive(True)
        self.cmb_modes.set_sensitive(True)

        self.stack_buttons.set_visible_child_name("start")
        self.isGUILocked = False

    def sendNotification(self, title, body):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon(name="pardus-image-writer"))
        notification.set_default_action("app.notification-response::focus")
        self.application.send_notification(self.application.get_application_id(), notification)
