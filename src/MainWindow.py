import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

from USBDeviceManager import USBDeviceManager

class WriteImageDialog(Gtk.Dialog):
    def __init__(self, parent, device, filename):
        Gtk.Dialog.__init__(self, "Emin misiniz?", parent, 0,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OK, Gtk.ResponseType.OK))
        
        # UI:
        self.set_default_size(350, 200)
        box = self.get_content_area()
        box.set_margin_start(11)
        box.set_margin_end(11)
        box.set_margin_top(11)
        box.set_margin_bottom(11)

        lbl_fileHeader = Gtk.Label()
        message = f"""
        Bu dosya:
        - <b>{filename}</b>

        Bu cihaza yazılacak:
        - <b>{device[1]} [ {device[2]} ]</b> <i>( {device[0]} )</i>
        
        <b>UYARI:</b> Cihazın içeriği tamamen silinecek!
        
        Onaylıyor musunuz?
        """
        lbl_fileHeader.set_markup(message)
        box.add(lbl_fileHeader)

        self.show_all()

class MainWindow:
    def __init__(self, application):
        # Gtk Builder
        self.builder = Gtk.Builder()
        self.builder.add_from_file("../ui/MainWindow.glade")
        self.builder.connect_signals(self)

        # Window
        self.window = self.builder.get_object("window")
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_application(application)
        self.window.connect("destroy", self.onDestroy)
        self.defineComponents()

        # Get inserted USB devices
        self.imgFilepath = self.usbDevice = ""
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

    # USB Methods
    def listUSBDevices(self):
        deviceList = self.usbManager.getUSBDevices()
        self.list_devices.clear()
        for device in deviceList:
            self.list_devices.append(device)

        self.cmb_devices.set_active(0)
        
        if len(deviceList) == 0:
            self.btn_start.set_sensitive(False)
            self.cmb_devices.set_tooltip_text(f"Bir cihaz takin.")
        elif self.imgFilepath:
            self.btn_start.set_sensitive(True)



    # UI Signals:
    def btn_selectISOFile_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select File",
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        
        fileFilter = Gtk.FileFilter()
        fileFilter.set_name("ISO Files")
        fileFilter.add_pattern("*.iso")
        dialog.add_filter(fileFilter)

        dialog.show()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()

            self.imgFilepath = filepath
            self.lbl_btn_selectISOFile.set_label(filepath.split('/')[-1])
            self.lbl_btn_selectISOFile.set_tooltip_text(filepath.split('/')[-1])
            
            if self.imgFilepath and self.usbDevice:
                self.btn_start.set_sensitive(True)
        
        dialog.destroy()

    def cmb_devices_changed(self, combobox):
        tree_iter = combobox.get_active_iter()
        if tree_iter:
            model = combobox.get_model()
            deviceInfo = model[tree_iter][:3]
            self.usbDevice = deviceInfo
            self.cmb_devices.set_tooltip_text(f"{deviceInfo[1]} [{deviceInfo[2]}] ({deviceInfo[0]})")
        else:
            self.btn_start.set_sensitive(False)

    def btn_start_clicked(self, button):
        # Ask if it is ok?
        dialog = WriteImageDialog(self.window, self.usbDevice, self.imgFilepath.split('/')[-1])
        response = dialog.run()

        # If cancel, turn to back
        if response == Gtk.ResponseType.OK:
            self.startProcess([
                "pkexec",
                os.path.dirname(os.path.abspath(__file__))+"/ImageWriter.py", 
                '/dev/'+self.usbDevice[0],
                self.imgFilepath
            ])
            self.btn_selectISOFile.set_sensitive(False)
            self.btn_start.set_sensitive(False)
            self.cmb_devices.set_sensitive(False)

        dialog.destroy()    

    # Handling Image Writer process
    def startProcess(self, params):
        pid, stdin, stdout, stderr = GLib.spawn_async(params,
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
        print(f"[{pid}] exit status:{status}")
        self.btn_selectISOFile.set_sensitive(True)
        self.btn_start.set_sensitive(True)
        self.cmb_devices.set_sensitive(True)

        self.listUSBDevices()

        if status == 0:
            self.pb_writingProgess.set_text(f"Basariyla Tamamlandi!")
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.INFO,
                Gtk.ButtonsType.OK,
                "Islem basarili!",
            )
            dialog.format_secondary_text(
                "USB Cihazi cikarabilirsiniz."
            )
            dialog.run()
            dialog.destroy()
        else:
            self.pb_writingProgess.set_text(f"Bir hata olustu!")
            self.pb_writingProgess.set_fraction(0)
            dialog = Gtk.MessageDialog(
                self.window,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                "Islem tamamlanamadi!",
            )
            dialog.format_secondary_text(
                "Lutfen cihazinizin bagli oldugundan emin olun."
            )
            dialog.run()
            dialog.destroy()