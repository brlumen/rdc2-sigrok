#!/bin/sh
#
# Apply the chipdip-rdc2-0064 driver to a libsigrok checkout.
#
# Usage: apply.sh <path-to-libsigrok-checkout>
#
# Copies src/hardware/chipdip-rdc2-0064/ and registers the driver in
# Makefile.am and configure.ac. Running it more than once is a no-op for the
# build files; the driver sources are always refreshed.

set -eu

DRIVER="chipdip-rdc2-0064"
SELF_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATCH="$SELF_DIR/libsigrok-build.patch"

die() {
	echo "apply.sh: $*" >&2
	exit 1
}

[ $# -eq 1 ] || die "usage: $0 <path-to-libsigrok-checkout>"
TARGET=$(CDPATH= cd -- "$1" 2>/dev/null && pwd) || die "no such directory: $1"

[ -f "$TARGET/configure.ac" ] && [ -f "$TARGET/Makefile.am" ] &&
	[ -d "$TARGET/src/hardware" ] ||
	die "$TARGET does not look like a libsigrok checkout"
[ -d "$SELF_DIR/$DRIVER" ] || die "missing driver sources in $SELF_DIR"
[ -f "$PATCH" ] || die "missing $PATCH"

# 1. Driver sources.
mkdir -p "$TARGET/src/hardware/$DRIVER"
cp "$SELF_DIR/$DRIVER/api.c" "$SELF_DIR/$DRIVER/protocol.c" \
	"$SELF_DIR/$DRIVER/protocol.h" "$TARGET/src/hardware/$DRIVER/"
echo "apply.sh: copied src/hardware/$DRIVER/"

# 2. Build system registration.
if grep -q "$DRIVER" "$TARGET/configure.ac" &&
		grep -q "$DRIVER" "$TARGET/Makefile.am"; then
	echo "apply.sh: build files already reference $DRIVER, nothing to do"
	exit 0
fi

if command -v git >/dev/null 2>&1 && [ -d "$TARGET/.git" ] &&
		git -C "$TARGET" apply --check "$PATCH" >/dev/null 2>&1; then
	git -C "$TARGET" apply "$PATCH"
	echo "apply.sh: applied libsigrok-build.patch"
	exit 0
fi

echo "apply.sh: patch does not apply, inserting the entries by anchor" >&2
command -v python3 >/dev/null 2>&1 || die "python3 is needed for the fallback"
TARGET="$TARGET" DRIVER="$DRIVER" python3 - <<'PYEOF'
import os
import sys

target = os.environ['TARGET']
driver = os.environ['DRIVER']

def insert(path, anchor, block, marker):
	with open(path, encoding='utf-8') as f:
		text = f.read()
	if marker in text:
		return False
	if anchor not in text:
		sys.exit('apply.sh: anchor %r not found in %s' % (anchor, path))
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text.replace(anchor, block + anchor, 1))
	return True

mk_block = (
	'if HW_CHIPDIP_RDC2_0064\n'
	'src_libdrivers_la_SOURCES += \\\n'
	'\tsrc/hardware/%s/protocol.h \\\n'
	'\tsrc/hardware/%s/protocol.c \\\n'
	'\tsrc/hardware/%s/api.c\n'
	'endif\n' % (driver, driver, driver))
insert(os.path.join(target, 'Makefile.am'),
	'if HW_CHRONOVU_LA\n', mk_block, 'HW_CHIPDIP_RDC2_0064')

cf_line = 'SR_DRIVER([ChipDip RDC2-0064], [%s], [libserialport libusb])\n' % driver
insert(os.path.join(target, 'configure.ac'),
	'SR_DRIVER([ChronoVu LA], [chronovu-la], [libusb libftdi])\n',
	cf_line, driver)
PYEOF
echo "apply.sh: registered $DRIVER in Makefile.am and configure.ac"
