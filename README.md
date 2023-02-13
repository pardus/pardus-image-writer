# pardus-image-writer

A tool for writing image files to removable storage devices such as USB drives and SD cards.

# Features
- User-friendly interface: pardus-image-writer features a graphical user interface that's easy to use and understand, even for those who are new to image writing tools.
- Works with both Windows ISOs and Linux ISOs: pardus-image-writer is capable of writing both Windows and Linux image files to removable storage devices, making it a versatile solution for a wide range of use cases.

# Dependencies

To use pardus-image-writer, you can use the following command to install necessary dependencies:

```bash
pip install setuptools pyudev
```

# Installation

To install pardus-image-writer, follow these steps:

If you are using Pardus or a Debian-based distribution, you can use the following steps to install pardus-image-writer:

1. Download the latest version of .deb file from [Releases](https://github.com/pardus/pardus-image-writer/releases) page.
2. Install the .deb file with Pardus Package Installer by double clicking on it. (or use `sudo apt install pardus-image-writer_0.4.0.Beta1_all.deb`)

If you are not using a Debian-based distribution, you can use the following steps to install pardus-image-writer:

```bash
$ git clone https://github.com/pardus/pardus-image-writer.git
$ cd pardus-image-writer
$ chmod +x setup.py
$ sudo ./setup.py install
```