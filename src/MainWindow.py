import os, sys, subprocess, requests
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

from USBDeviceManager import USBDeviceManager

import locale
from locale import gettext as tr

# Translation Constants:
APPNAME = "pardus-image-writer"
TRANSLATIONS_PATH = "/usr/share/locale"
SYSTEM_LANGUAGE = os.environ.get("LANG")

# Translation functions:
locale.bindtextdomain(APPNAME, TRANSLATIONS_PATH)
locale.textdomain(APPNAME)
locale.setlocale(locale.LC_ALL, SYSTEM_LANGUAGE)

class MainWindow:
    def __init__(self, application, file = ""):
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
        self.writeMode = "ImageWriter.py" # ImageWriter.py for DD Mode, ISOCopier.py for ISO Mode

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

        # Set application:
        self.application = application

        # Show Screen:
        self.window.show_all()
    
    # Window methods:
    def onDestroy(self, action):
        self.window.get_application().quit()
    
    def defineComponents(self):
        self.stack_windows = self.builder.get_object("stack_windows")

        self.list_devices = self.builder.get_object("list_devices")
        self.cmb_devices = self.builder.get_object("cmb_devices")
        self.btn_selectISOFile = self.builder.get_object("btn_selectISOFile")
        self.lbl_btn_selectISOFile = self.builder.get_object("lbl_btn_selectISOFile")
        self.rb_ddMode = self.builder.get_object("rb_ddMode")
        self.rb_isoMode = self.builder.get_object("rb_isoMode")
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



    # UI Signals:
    def rb_ddMode_toggled(self, rb):
        if self.rb_ddMode.get_active():
            self.writeMode = "ImageWriter.py"
        else:
            self.writeMode = "ISOCopier.py"

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
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()

            self.imgFilepath = filepath
            self.lbl_btn_selectISOFile.set_label(filepath.split('/')[-1])
            self.fileType = filepath.split(".")[-1]
            if self.fileType == "img":
                self.rb_isoMode.set_sensitive(False)
                self.rb_ddMode.set_active(True)
            else:
                self.rb_isoMode.set_sensitive(True)
            
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
    
    # Buttons:
    def btn_start_clicked(self, button):
        self.prepareWriting()
    
    def btn_cancel_clicked(self, button):
        self.cancelWriting()
    
    def btn_exit_clicked(self, button):
        self.window.get_application().quit()
    
    def btn_write_new_file_clicked(self, button):
        self.stack_windows.set_visible_child_name("main")
    
    def btn_information_clicked(self,button):
        self.dialog_about.run()
        self.dialog_about.hide()



    def onCheckingIntegrityFinished(self):
        # Check ISO has md5 on list:
        isISOGood = False
        for line in self.md5sumlist:
            if line.split()[0] == self.md5_of_file.split()[0]:
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
            '/dev/'+self.usbDevice[0],
        ])

    def prepareWriting(self):
        # Ask if it is ok?
        self.dlg_lbl_filename.set_markup("- <b>{}</b>".format(self.imgFilepath.split('/')[-1]))
        self.dlg_lbl_disk.set_markup("- <b>{} [ {} ]</b> <i>( /dev/{} )</i>".format(self.usbDevice[1], self.usbDevice[2], self.usbDevice[0]))

        response = self.dialog_write.run()
        self.dialog_write.hide()
        if response == Gtk.ResponseType.YES:
            if self.cb_checkIntegrity.get_active():
                self.lockGUI(disableStart=True)
                self.dialog_integrity.show_all()
                self.finishedProcesses = 0

                self.md5sumlist = []
                self.md5_of_file = ""             
                
                # Check MD5SUM of the ISO file:
                def on_md5_stdout(source, condition):
                    if condition == GLib.IO_HUP:
                        return False
                    
                    self.md5_of_file = source.readline().strip()
                    return True
                def on_md5_finished(pid, status):
                    self.finishedProcesses += 1
                    if self.finishedProcesses == 2:
                        self.onCheckingIntegrityFinished()

                
                md5_pid, _, md5_stdout, _ = GLib.spawn_async(["md5sum", self.imgFilepath],
                                    flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN | GLib.SPAWN_DO_NOT_REAP_CHILD,
                                    standard_input=False, standard_output=True, standard_error=False)
                GLib.io_add_watch(GLib.IOChannel(md5_stdout), GLib.IO_IN | GLib.IO_HUP, on_md5_stdout)
                GLib.child_watch_add(GLib.PRIORITY_DEFAULT, md5_pid, on_md5_finished)
                
                # Get MD5SUMS from pardus.org.tr:
                try:
                    result = requests.get("http://indir.pardus.org.tr/PARDUS/MD5SUMS")
                    self.md5sumlist = result.text.splitlines()
                    on_md5_finished(0,0)
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
            else:
                self.startWriting()
    
    def cancelWriting(self):
        subprocess.call(["pkexec", "kill", "-9", str(self.writerProcessPID)])
    
    def onTimeout(self, user_data):
        self.pb_writingProgess.pulse()
        return True
    
    def startProcess(self, params):
        if self.writeMode == "ISOCopier.py":
            self.pb_writingProgess.set_text(tr("Copying files..."))
            self.pb_writingProgess.pulse()
            self.timeoutID = GLib.timeout_add(100, self.onTimeout, None)
        
        self.writerProcessPID, _, stdout, _ = GLib.spawn_async(params,
                                    flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN | GLib.SPAWN_DO_NOT_REAP_CHILD,
                                    standard_input=False, standard_output=True, standard_error=True)
        
        if self.writeMode == "ImageWriter.py":
            GLib.io_add_watch(GLib.IOChannel(stdout), GLib.IO_IN | GLib.IO_HUP, self.onProcessStdout)
        
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT, self.writerProcessPID, self.onProcessExit)

    def onProcessStdout(self, source, condition):
        if condition == GLib.IO_HUP:
            return False
        
        line = source.readline().strip()
        written, total = line.split()
        written = int(written)
        total = int(total)
        percent = 0
        if total > 0:
            percent = written / total

        self.pb_writingProgess.set_text("{}MB / {}MB (%{})".format(round(written/1000/1000), round(total/1000/1000), int(percent*100)))
        self.pb_writingProgess.set_fraction(percent)
        return True
    
    def onProcessExit(self, pid, status):
        self.unlockGUI()
        self.listUSBDevices()

        self.pb_writingProgess.set_text("0%")
        self.pb_writingProgess.set_fraction(0)
        GLib.source_remove(self.timeoutID) # stop pulse timeout

        if status == 0:
            self.pb_writingProgess.set_text("0%")
            self.sendNotification(tr("Writing process is finished."), tr("You can eject the USB disk."))
            self.stack_windows.set_visible_child_name("finished")
        elif status != 15 and status != 32256: # these are cancelling or auth error.
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

        self.rb_ddMode.set_sensitive(False)
        self.rb_isoMode.set_sensitive(False)

        self.stack_buttons.set_visible_child_name("cancel")
        self.isGUILocked = True
        
    def unlockGUI(self):
        self.btn_selectISOFile.set_sensitive(True)
        self.cmb_devices.set_sensitive(True)
        self.cb_checkIntegrity.set_sensitive(True)

        self.rb_ddMode.set_sensitive(True)
        if self.fileType == "iso":
            self.rb_isoMode.set_sensitive(True)

        self.stack_buttons.set_visible_child_name("start")
        self.isGUILocked = False
    
    def sendNotification(self, title, body):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon(name="pardus-image-writer"))
        notification.set_default_action("app.notification-response::focus")
        self.application.send_notification(self.application.get_application_id(), notification)