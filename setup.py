#!/usr/bin/env python3
from setuptools import setup, find_packages

data_files = [
    ("/usr/share/applications/", ["tr.org.pardus.image-writer.desktop"]),
    ("/usr/share/locale/tr_TR/LC_MESSAGES/", ["translations/tr_TR/LC_MESSAGES/pardus-image-writer.mo"]),
    ("/usr/share/pardus/pardus-image-writer/", ["icon.svg"]),
    ("/usr/share/pardus/pardus-image-writer/src", ["src/main.py", "src/MainWindow.py", "src/ImageWriter.py", "src/USBDeviceManager.py"]),
    ("/usr/share/pardus/pardus-image-writer/ui", ["ui/MainWindow.glade"]),
    ("/usr/bin/", ["pardus-image-writer"]),
]

setup(
    name="Pardus Image Writer",
    version="0.1",
    packages=find_packages(),
    scripts=["pardus-image-writer"],
    install_requires=["PyGObject"],
    data_files=data_files,
    author="Emin Fedar",
    author_email="emin.fedar@pardus.org.tr",
    description="Pardus ISO Image Writer.",
    license="GPLv3",
    keywords="iso usb image burn write",
    url="https://www.pardus.org.tr",
)
