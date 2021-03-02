#!/usr/bin/python3

import sys, os
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

from MainWindow import MainWindow


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="tr.org.pardus.image-writer",
                         flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE, **kwargs)
        self.window = None

    def do_activate(self):
        self.window = MainWindow(self)

    def do_open(self, files, filecount, hint):
        if filecount == 1:
            file = files[0]
            if os.path.exists(file.get_path()):
                fileFormat = file.get_basename().split(".")[-1]
                if fileFormat == "iso":
                    self.window = MainWindow(self, file.get_path())
                else:
                    print("Only .iso files.")
            else:
                print("File not exists : " + file.get_path())
        else:
            print("Only one file.")


if __name__ == "__main__":
    app = Application()
    app.run(sys.argv)
