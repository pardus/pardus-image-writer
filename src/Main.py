#!/usr/bin/python3

import os
import sys
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk, GLib

from MainWindow import MainWindow


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            application_id="tr.org.pardus.image-writer",
            flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE,
            **kwargs,
        )
        self.window = None
        GLib.set_prgname("tr.org.pardus.image-writer")

    def do_activate(self):
        self.window = MainWindow(self)

    def do_open(self, files, filecount, hint):
        if filecount != 1:
            print("Only one file.")
            return

        file = files[0]

        if not os.path.exists(file.get_path()):
            print("File does not exist: " + file.get_path())
            return

        fileFormat = file.get_basename().split(".")[-1]

        supported_extensions = ["iso", "img"]

        if fileFormat not in supported_extensions:
            print(
                "Supported file extensions: {}".format(", ".join(supported_extensions))
            )
            return

        self.window = MainWindow(self, file.get_path())


app = Application()
app.run(sys.argv)
