# Pardus Image Writer

Pardus Image Writer is an application for burn ISO and IMG files to USB Flash sticks.

It is currently a work in progress. Maintenance is done by <a href="https://www.pardus.org.tr/">Pardus</a> team.

[![Packaging status](https://repology.org/badge/vertical-allrepos/pardus-image-writer.svg)](https://repology.org/project/pardus-image-writer/versions)

### **Dependencies**

This application is developed based on Python3 and GTK+ 3. Dependencies:
```bash
gir1.2-glib-2.0 gir1.2-gtk-3.0 python3-gi python3-requests python3-pyudev parted rsync
```

### **Run Application from Source**

Install dependencies
```bash
sudo apt install gir1.2-glib-2.0 gir1.2-gtk-3.0 python3-gi python3-requests python3-pyudev parted rsync
```
Clone the repository
```bash
git clone https://github.com/pardus/pardus-image-writer.git ~/pardus-image-writer
```
Run application
```bash
python3 ~/pardus-image-writer/src/Main.py
```

### **Build deb package**

```bash
sudo apt install devscripts git-buildpackage
sudo mk-build-deps -ir
gbp buildpackage --git-export-dir=/tmp/build/pardus-image-writer -us -uc
```

### **Screenshots**

![Pardus Image Writer 1](screenshots/pardus-image-writer-1.png)

![Pardus Image Writer 2](screenshots/pardus-image-writer-2.png)
