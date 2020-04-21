import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

from USBDeviceManager import USBDeviceManager
from ImageWriter import ImageWriter

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

        # Define Image Writer
        self.imageWriter = ImageWriter()

        # Get inserted USB devices
        self.usbManager = USBDeviceManager()
        self.listUSBDevices()

        # Show Screen:
        self.window.show_all()
    
    # Window methods:
    def onDestroy(self, action):
        self.window.get_application().quit()
    
    def defineComponents(self):
        self.list_devices = self.builder.get_object("list_devices")
        self.cmb_devices = self.builder.get_object("cmb_devices")
        self.btn_selectISOFile = self.builder.get_object("btn_selectISOFile")
    

    # USB Methods
    def listUSBDevices(self):
        deviceList = self.usbManager.getUSBDevices()
        for device in deviceList:
            self.list_devices.append(device)

        if len(deviceList) > 0:
            self.cmb_devices.set_active(0)
        pass




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

            self.imageWriter.setFilepath(filepath)
            print(filepath)
            print(filepath.split('/'))
            print(filepath.split('/')[-1])
            self.btn_selectISOFile.set_label(filepath.split('/')[-1])
        
        dialog.destroy()

    def cmb_devices_changed(self, combobox):
        tree_iter = combobox.get_active_iter()
        model = combobox.get_model()
        deviceInfo = model[tree_iter][:3]
        print(f"{deviceInfo[0]} {deviceInfo[1]} {deviceInfo[2]}")
        self.imageWriter.setDevice(deviceInfo)

    def btn_start_clicked(self, button):
        # Ask if it is ok?
        dialog = WriteImageDialog(self.window, self.imageWriter.device, self.imageWriter.filepath.split('/')[-1])
        response = dialog.run()

        # If cancel, turn to back
        if response == Gtk.ResponseType.OK:
            print("TEZ YAZMA BASLASIN :)")

        dialog.destroy()
