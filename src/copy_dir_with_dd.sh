#!/bin/sh

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
	# !!! IMPORTANT !!!
	# Works best if the USB disk not mounted as fuseblk. Mount something like ntfs3 to transfer the files faster.(e.g. mount -t ntfs3 ...)

	dd if="$file" status=none bs=64K | pv --numeric --bytes --buffer-size 64K | dd of="$TARGET/$file" oflag=nocache status=none bs=64K || return $?
	COPIED_FILES=$((COPIED_FILES+1))
	echo "COPIED:$COPIED_FILES:$TOTAL_FILE_COUNT"
done
find * -type l -exec cp -P {} "$TARGET/{}" \;

sync

