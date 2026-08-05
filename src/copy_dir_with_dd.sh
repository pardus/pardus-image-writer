#!/bin/bash
# bash is required: the NUL delimited "read -d" below is not POSIX sh.
# Copy a mounted ISO tree onto the mounted USB partition, reporting progress.
#
# Progress protocol on stdout, consumed by ISOCopier.py:
#   TOTAL_BYTES:<n>          once, before copying
#   <n>                      copied bytes so far (printed by pv on stderr)
#   COPIED:<done>:<total>    after every file
#
# The loop is driven by 'find -print0' + 'read', so file names containing
# spaces, tabs or quotes are copied correctly.

# pipefail is what makes a failure of the reading 'dd' or of 'pv' visible: the
# status of a pipeline is the status of its last command, so without it a
# truncated file would be counted as copied, get a boot loader installed on top
# and be reported to the user as a finished disk.
set -u -o pipefail

SOURCE=$1
TARGET=$2

if [ ! -d "$SOURCE" ] || [ ! -d "$TARGET" ]; then
	echo "copy_dir_with_dd.sh: source or target directory is missing" >&2
	exit 1
fi

cd "$SOURCE" || exit 1

COPIED_FILES=0
TOTAL_FILE_COUNT=$(find . -type f | wc -l)
TOTAL_BYTES=$(du -sb "$SOURCE" | cut -f1)

echo "TOTAL_BYTES:$TOTAL_BYTES"

# Recreate the directory tree first, so every copy below has its parent.
find . -type d -print0 | while IFS= read -r -d '' directory; do
	mkdir -p "$TARGET/$directory" || exit 1
done || exit 1

# 'find -print0' with a NUL delimited read keeps whole file names intact.
find . -type f -print0 | while IFS= read -r -d '' file; do
	# !!! IMPORTANT !!!
	# Works best if the USB disk not mounted as fuseblk. Mount something like ntfs3 to transfer the files faster.(e.g. mount -t ntfs3 ...)

	dd if="$file" status=none bs=64K \
		| pv --numeric --bytes --buffer-size 64K \
		| dd of="$TARGET/$file" oflag=nocache status=none bs=64K || exit 1

	COPIED_FILES=$((COPIED_FILES + 1))
	echo "COPIED:$COPIED_FILES:$TOTAL_FILE_COUNT"
done || exit 1

# FAT32 cannot store symbolic links, so a link the ISO ships is not an error:
# failing here would throw away a copy that is otherwise complete.  Replacing
# the link with its target is only safe for a regular file - an ISO carries
# links like "debian -> ." that would make the copy recurse forever - so
# anything else is reported and skipped.
find . -type l -print0 | while IFS= read -r -d '' link; do
	if cp -P "$link" "$TARGET/$link" 2>/dev/null; then
		continue
	fi

	if [ -f "$link" ] && cp -L "$link" "$TARGET/$link" 2>/dev/null; then
		continue
	fi

	echo "copy_dir_with_dd.sh: skipped symbolic link $link, the target filesystem does not support it" >&2
done || exit 1

sync
