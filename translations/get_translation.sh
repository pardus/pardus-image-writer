#!/bin/sh
xgettext --language=Python --keyword=tr --keyword=N_ --output=translation.pot ../src/MainWindow.py
xgettext --language=Glade --output=translation.pot ../ui/MainWindow.glade -j