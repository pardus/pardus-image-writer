#!/usr/bin/env python3
from setuptools import setup, find_packages, os, subprocess
from shutil import copyfile

changelog = 'debian/changelog'
if os.path.exists(changelog):
    head = open(changelog).readline()
    try:
        version = head.split("(")[1].split(")")[0]
    except:
        print("debian/changelog format is wrong for get version")
        version = ""
    f = open('src/__version__', 'w')
    f.write(version)
    f.close()

copyfile("icon.svg", "pardus-image-writer.svg")

def create_mo_files():
    podir = "po"
    mo = []
    for po in os.listdir(podir):
        if po.endswith(".po"):
            os.makedirs("{}/{}/LC_MESSAGES".format(podir, po.split(".po")[0]), exist_ok=True)
            mo_file = "{}/{}/LC_MESSAGES/{}".format(podir, po.split(".po")[0], "pardus-image-writer.mo")
            msgfmt_cmd = 'msgfmt {} -o {}'.format(podir + "/" + po, mo_file)
            subprocess.call(msgfmt_cmd, shell=True)
            mo.append(("/usr/share/locale/" + po.split(".po")[0] + "/LC_MESSAGES",
                       ["po/" + po.split(".po")[0] + "/LC_MESSAGES/pardus-image-writer.mo"]))
    return mo

data_files = [
    ("/usr/share/applications/", ["tr.org.pardus.image-writer.desktop"]),
    ("/usr/share/locale/tr/LC_MESSAGES/", ["translations/tr/LC_MESSAGES/pardus-image-writer.mo"]),
    ("/usr/share/pardus/pardus-image-writer/", ["icon.svg", "main.svg", "iso.svg", "disk.svg", "settings.svg", "uefi-ntfs.img"]),
    ("/usr/share/pardus/pardus-image-writer/src",
     ["src/main.py", "src/MainWindow.py", "src/ISOCopier.py", "src/ImageWriter.py", "src/USBDeviceManager.py",
      "src/WinUSB.py", "src/__version__"]),
    ("/usr/share/pardus/pardus-image-writer/ui", ["ui/MainWindow.glade"]),
    ("/usr/share/polkit-1/actions", ["tr.org.pardus.pkexec.pardus-image-writer.policy"]),
    ("/usr/bin/", ["pardus-image-writer"]),
    ("/usr/share/icons/hicolor/scalable/apps/", ["pardus-image-writer.svg"]),
] + create_mo_files()

setup(
    name="Pardus Image Writer",
    version=version,
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
