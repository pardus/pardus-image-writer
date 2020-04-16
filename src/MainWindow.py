import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

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

        # Show Screen:
        self.window.show_all()
    
    def onDestroy(self, action):
        self.window.get_application().quit()
    
    def defineComponents(self):
        self.list_devices = self.builder.get_object("list_devices")
    
    def getUSBDevices(self):
        pass
