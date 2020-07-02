#!/usr/bin/env python3
from setuptools import setup, find_packages

data_files = [
    ("/usr/share/applications/", ["tr.org.pardus.image-writer.desktop"]),
    ("/usr/share/locale/tr/LC_MESSAGES/", ["translations/tr/LC_MESSAGES/pardus-image-writer.mo"]),
    ("/usr/share/pardus/pardus-image-writer/", ["icon.svg", "main.svg"]),
    ("/usr/share/pardus/pardus-image-writer/src", ["src/main.py", "src/MainWindow.py", "src/ImageWriter.py", "src/USBDeviceManager.py"]),
    ("/usr/share/pardus/pardus-image-writer/ui", ["ui/MainWindow.glade"]),
    ("/usr/share/polkit-1/actions", ["tr.org.pardus.pkexec.pardus-image-writer.policy"]),
    ("/usr/bin/", ["pardus-image-writer"])
]

setup(
    name="Pardus Image Writer",
    version="0.2.0~Beta1",
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
