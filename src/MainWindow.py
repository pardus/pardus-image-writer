import os, sys
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
        self.builder.add_from_file("/usr/share/pardus/pardus-image-writer/ui/MainWindow.glade")
        self.builder.connect_signals(self)

        # Window
        self.window = self.builder.get_object("window")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_application(application)
        self.window.connect("destroy", self.onDestroy)
        self.defineComponents()

        # Get inserted USB devices
        self.imgFilepath = file
        if file:
            self.lbl_btn_selectISOFile.set_label(file.split('/')[-1])
            
        self.usbDevice = [""]
        self.usbManager = USBDeviceManager()
        self.usbManager.setUSBRefreshSignal(self.listUSBDevices)
        self.listUSBDevices()

        # Show Screen:
        self.window.show_all()
    
    # Window methods:
    def onDestroy(self, action):
        self.usbManager.usbListenTimer.cancel()
        self.window.get_application().quit()
    
    def defineComponents(self):
        self.list_devices = self.builder.get_object("list_devices")
        self.cmb_devices = self.builder.get_object("cmb_devices")
        self.btn_selectISOFile = self.builder.get_object("btn_selectISOFile")
        self.lbl_btn_selectISOFile = self.builder.get_object("lbl_btn_selectISOFile")
        self.btn_start = self.builder.get_object("btn_start")
        self.pb_writingProgess = self.builder.get_object("pb_writingProgress")

        # Dialog:
        self.dialog_write = self.builder.get_object("dialog_write")
        self.dlg_lbl_filename = self.builder.get_object("dlg_lbl_filename")
        self.dlg_lbl_disk = self.builder.get_object("dlg_lbl_disk")

    # USB Methods
    def listUSBDevices(self):
        deviceList = self.usbManager.getUSBDevices()
        self.list_devices.clear()
        for device in deviceList:
            self.list_devices.append(device)

        self.cmb_devices.set_active(0)
        
        if len(deviceList) == 0:
            self.btn_start.set_sensitive(False)
        elif self.imgFilepath:
            self.btn_start.set_sensitive(True)



    # UI Signals:
    def btn_selectISOFile_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        
        fileFilter = Gtk.FileFilter()
        fileFilter.set_name("*.iso")
        fileFilter.add_pattern("*.iso")
        dialog.add_filter(fileFilter)

        dialog.show()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()

            self.imgFilepath = filepath
            self.lbl_btn_selectISOFile.set_label(filepath.split('/')[-1])
            
            if self.imgFilepath and self.usbDevice:
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

    def btn_start_clicked(self, button):
        # Ask if it is ok?
        self.dlg_lbl_filename.set_markup(f"- <b>{self.imgFilepath.split('/')[-1]}</b>")
        self.dlg_lbl_disk.set_markup(f"- <b>{self.usbDevice[1]} [ {self.usbDevice[2]} ]</b> <i>( /dev/{self.usbDevice[0]} )</i>")

        response = self.dialog_write.run()

        # If cancel, turn to back
        if response == Gtk.ResponseType.YES:
            self.startProcess([
                "pkexec",
                os.path.dirname(os.path.abspath(__file__))+"/ImageWriter.py", 
                '/dev/'+self.usbDevice[0],
                self.imgFilepath
            ])
            self.btn_selectISOFile.set_sensitive(False)
            self.btn_start.set_sensitive(False)
            self.cmb_devices.set_sensitive(False)

        self.dialog_write.hide()

    # Handling Image Writer process
    def startProcess(self, params):
        pid, _, stdout, _ = GLib.spawn_async(params,
                                    flags=GLib.SPAWN_SEARCH_PATH | GLib.SPAWN_LEAVE_DESCRIPTORS_OPEN | GLib.SPAWN_DO_NOT_REAP_CHILD,
                                    standard_input=False, standard_output=True, standard_error=True)
        GLib.io_add_watch(GLib.IOChannel(stdout), GLib.IO_IN | GLib.IO_HUP, self.onProcessStdout)
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT, pid, self.onProcessExit)
    
    def onProcessStdout(self, source, condition):
        if condition == GLib.IO_HUP:
            return False
        
        line = source.readline().strip()
        written, total = line.split()
        written = int(written)
        total = int(total)
        percent = written / total

        self.pb_writingProgess.set_text(f"{round(written/1000/1000)}MB / {round(total/1000/1000)}MB (%{int(percent*100)})")
        self.pb_writingProgess.set_fraction(percent)
        #print(f"[stdout]: {source.readline()}")
        return True
    
    def onProcessExit(self, pid, status):
        self.btn_selectISOFile.set_sensitive(True)
        self.btn_start.set_sensitive(True)
        self.cmb_devices.set_sensitive(True)

        self.listUSBDevices()

        if status == 0:
            self.pb_writingProgess.set_text(tr("Success!"))
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.INFO,
                Gtk.ButtonsType.OK,
                tr("Writing process ended successfully."),
            )
            dialog.format_secondary_text(
                tr("You can eject the USB disk.")
            )
            dialog.run()
            dialog.destroy()
        else:
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