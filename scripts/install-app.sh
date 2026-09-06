#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
#
# install-app.sh -- wrap the PulseView built by build-macos.sh into a macOS
# application bundle, so that it can be started from /Applications, Spotlight
# and the Dock like any other app.
#
# The bundle is a thin launcher: it sets the same environment as
# scripts/env.sh (prefix bin on PATH, plain XDG_DATA_DIRS so that only the
# decoders of this stack are loaded) and execs $PREFIX/bin/pulseview. Nothing
# is copied, so re-running build-macos.sh updates the app as well. Re-run this
# script only when the prefix moves.
#
# Usage: scripts/install-app.sh [--prefix DIR] [--dir DIR]
#   --prefix DIR   sigrok stack prefix. Default: $OPENLA_PREFIX or ~/.local/openla
#   --dir DIR      where to put PulseView.app. Default: /Applications
#                  (falls back to ~/Applications when not writable)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
PREFIX="${OPENLA_PREFIX:-$HOME/.local/openla}"
APP_DIR=""
ICON_SRC="${REPO_ROOT}/.build/src/pulseview/icons/pulseview.svg"

die() { echo "install-app.sh: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
	case "$1" in
	--prefix)   [ $# -ge 2 ] || die "--prefix needs an argument"; PREFIX="$2"; shift 2 ;;
	--prefix=*) PREFIX="${1#*=}"; shift ;;
	--dir)      [ $# -ge 2 ] || die "--dir needs an argument"; APP_DIR="$2"; shift 2 ;;
	--dir=*)    APP_DIR="${1#*=}"; shift ;;
	-h|--help)  sed -n '5,20p' "$0"; exit 0 ;;
	*)          die "unknown option: $1" ;;
	esac
done

[ -x "${PREFIX}/bin/pulseview" ] || die "${PREFIX}/bin/pulseview not found; run scripts/build-macos.sh first"

if [ -z "${APP_DIR}" ]; then
	if [ -w /Applications ]; then
		APP_DIR=/Applications
	else
		APP_DIR="${HOME}/Applications"
	fi
fi
mkdir -p "${APP_DIR}"
APP="${APP_DIR}/PulseView.app"

rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"

# Launcher. Finder does not pass the shell environment, so it is set here.
cat > "${APP}/Contents/MacOS/PulseView" <<EOF
#!/bin/bash
export OPENLA_PREFIX="${PREFIX}"
export PATH="${PREFIX}/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export XDG_DATA_DIRS="/usr/local/share:/usr/share"
exec "${PREFIX}/bin/pulseview" "\$@"
EOF
chmod 755 "${APP}/Contents/MacOS/PulseView"

version="$("${PREFIX}/bin/pulseview" --version 2>/dev/null | head -1 | sed -E 's/^[^0-9]*([0-9][^ ]*).*/\1/')"
[ -n "${version}" ] || version="0.5.0"

cat > "${APP}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key>            <string>PulseView</string>
	<key>CFBundleDisplayName</key>     <string>PulseView</string>
	<key>CFBundleIdentifier</key>      <string>org.sigrok.pulseview.openla</string>
	<key>CFBundleExecutable</key>      <string>PulseView</string>
	<key>CFBundleIconFile</key>        <string>PulseView</string>
	<key>CFBundlePackageType</key>     <string>APPL</string>
	<key>CFBundleShortVersionString</key> <string>${version}</string>
	<key>CFBundleVersion</key>         <string>${version}</string>
	<key>LSMinimumSystemVersion</key>  <string>12.0</string>
	<key>NSHighResolutionCapable</key> <true/>
	<key>CFBundleDocumentTypes</key>
	<array>
		<dict>
			<key>CFBundleTypeName</key>  <string>sigrok session</string>
			<key>CFBundleTypeRole</key>  <string>Viewer</string>
			<key>CFBundleTypeExtensions</key> <array><string>sr</string></array>
		</dict>
	</array>
</dict>
</plist>
EOF

# Icon: render the upstream SVG into an .icns. Skipped when the tools or the
# source tree are missing; the app then shows the generic icon.
if [ -f "${ICON_SRC}" ] && command -v qlmanage >/dev/null && command -v iconutil >/dev/null; then
	tmp="$(mktemp -d)"
	trap 'rm -rf "${tmp}"' EXIT
	# The upstream SVG is 48x48 without a viewBox; give it one so that it
	# scales to the full 1024 px canvas instead of sitting tiny in a corner.
	sed -E 's/<svg /<svg viewBox="0 0 48 48" /; s/ height="48"/ height="1024"/; s/ width="48"/ width="1024"/' \
		"${ICON_SRC}" > "${tmp}/pulseview.svg"
	qlmanage -t -s 1024 -o "${tmp}" "${tmp}/pulseview.svg" >/dev/null 2>&1 || true
	png="${tmp}/pulseview.svg.png"
	if [ -f "${png}" ]; then
		mkdir -p "${tmp}/PulseView.iconset"
		for s in 16 32 128 256 512; do
			sips -z "$s" "$s" "${png}" --out "${tmp}/PulseView.iconset/icon_${s}x${s}.png" >/dev/null
			d=$((s * 2))
			sips -z "$d" "$d" "${png}" --out "${tmp}/PulseView.iconset/icon_${s}x${s}@2x.png" >/dev/null
		done
		iconutil -c icns "${tmp}/PulseView.iconset" -o "${APP}/Contents/Resources/PulseView.icns"
	fi
fi

# Let LaunchServices pick the new bundle up right away.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "${APP}" >/dev/null 2>&1 || true
touch "${APP}"

echo "installed ${APP} -> ${PREFIX}/bin/pulseview (${version})"
echo "open it from Finder/Spotlight, or: open -a PulseView --args -d chipdip-rdc2-0064"
