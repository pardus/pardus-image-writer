#!/bin/sh

# Works best if the USB disk not mounted as fuseblk. Mount something like ntfs3 to transfer the files faster.

SOURCE=$1
TARGET=$2

echo "Source: $SOURCE"
echo "Target: $TARGET"

cd "$SOURCE"

COPIED_FILES=0
TOTAL_FILE_COUNT=$(find * -type f | wc -l)

TOTAL_BYTES=$(du -sb "$SOURCE" | cut -f1)

echo "TOTAL_BYTES:$TOTAL_BYTES"

find * -type d -exec mkdir -p "$TARGET/{}" \;
for file in $(find * -type f)
do
	# dd if="$file" of="$TARGET/$file" bs=8M iflag=noatime,dsync oflag=noatime,direct status=progress 2>&1 | sed -n 's/\([0-9]\+\) bytes.*/BYTES:\1/p' # print written bytes
	dd if="$file" status=none bs=8M | pv -n -b -B 8388608 | dd of="$TARGET/$file" oflag=nocache status=none bs=8M || return $?
	COPIED_FILES=$((COPIED_FILES+1))
	echo "COPIED:$COPIED_FILES:$TOTAL_FILE_COUNT"
done
find * -type l -exec cp -P {} "$TARGET/{}" \;

sync

