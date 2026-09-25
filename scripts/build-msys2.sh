#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
#
# build-msys2.sh -- reproducible build of the sigrok stack for rdc2-sigrok on
# Windows, from an MSYS2 UCRT64 shell.
#
# Windows counterpart of build-macos.sh.  Same pinned commits
# (scripts/versions.env), same patches (scripts/patches), same out-of-tree
# driver hook (sigrok/apply.sh), same .build/ layout and stamps, same private
# prefix; only the package manager (pacman instead of Homebrew) and the
# platform plumbing differ:
#
#   - Windows has no rpath: sigrok-cli.exe and pulseview.exe find the
#     libsigrok*.dll next to themselves in $PREFIX/bin and everything else
#     (glib, Qt, boost, python) in $MINGW_PREFIX/bin, which the MSYS2 shell
#     puts on PATH.  Outside that shell the binaries need the same PATH.
#   - The compiled-in POSIX decoder path means nothing to a native binary;
#     libsigrokdecode finds $PREFIX/share/libsigrokdecode/decoders through
#     GLib's data dirs instead.  GLib on Windows derives those from the DLL
#     location unless XDG_DATA_DIRS is set -- and the MSYS2 profile sets it
#     (for bash-completion), so inside an MSYS2 shell $PREFIX/share has to be
#     prepended to it.  env.sh does that; this script does it for its own
#     verification run.
#   - libserialport is built from source (macOS uses the Homebrew bottle):
#     release 0.1.2 cannot report the USB VID/PID of a COM port whose
#     driver owns the whole USB device, which is how usbser has to be bound
#     to this board (see windows/rdc2-0064-usbser.inf), so the driver's
#     VID/PID scan found nothing.  scripts/patches/libserialport-0001-*.patch
#     fixes that; 0002 and 0003 take the USB string descriptor reads and the
#     GetCommState/SetCommState round trip out of the open path, because
#     the board's firmware dies from control transfers (docs/protocol.md).
#   - MSYS2 ships shared libraries only.  PulseView's CMakeLists forces
#     static pkg-config libs and static Qt plugins on WIN32 (an MXE
#     assumption); scripts/patches/pulseview-0003-*.patch makes both follow
#     the actual library type, and this script passes
#     -DSTATIC_PKGDEPS_LIBS=FALSE.
#
# Prerequisites: MSYS2 (https://www.msys2.org, e.g. "winget install
# MSYS2.MSYS2") and its UCRT64 shell, C:\msys64\ucrt64.exe.  From any other
# shell:
#   MSYSTEM=UCRT64 C:\msys64\usr\bin\bash.exe -lc 'cd /c/path/to/rdc2-sigrok && scripts/build-msys2.sh'
#
# See build-macos.sh for the driver-hook contract and the .build/ layout;
# they are identical.  No hardware is touched at any point.

set -euo pipefail

#-----------------------------------------------------------------------------
# Constants and defaults
#-----------------------------------------------------------------------------

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
BUILD_ROOT="${REPO_ROOT}/.build"
SRC_DIR="${BUILD_ROOT}/src"
OBJ_DIR="${BUILD_ROOT}/build"
STAMP_DIR="${BUILD_ROOT}/stamps"
LOG_DIR="${BUILD_ROOT}/logs"
PATCH_DIR="${SCRIPT_DIR}/patches"
DRIVER_HOOK="${REPO_ROOT}/sigrok/apply.sh"

ALL_COMPONENTS="libserialport libsigrok libsigrokdecode sigrok-cli pulseview"

PREFIX="${RDC2_SIGROK_PREFIX:-${HOME}/.local/rdc2-sigrok}"
COMPONENTS=""
CLEAN=0
DO_PACMAN=1
JOBS="$(nproc 2>/dev/null || echo 4)"

# pacman packages required to build the stack.  MSYS_DEPS are plain msys
# packages (the POSIX build tools); MINGW_DEPS get the $MINGW_PACKAGE_PREFIX
# of the current shell (mingw-w64-ucrt-x86_64-*) prepended.
MSYS_DEPS="autotools make git patch"
MINGW_DEPS="gcc pkgconf cmake ninja glib2 libzip libusb libftdi hidapi glibmm \
doxygen boost qt6-base qt6-svg qt6-tools python"

#-----------------------------------------------------------------------------
# Output helpers
#-----------------------------------------------------------------------------

if [ -t 1 ]; then C_B=$'\033[1m'; C_G=$'\033[32m'; C_Y=$'\033[33m'; C_R=$'\033[31m'; C_0=$'\033[0m'
else C_B=""; C_G=""; C_Y=""; C_R=""; C_0=""; fi

step() { printf '%s==> %s%s\n' "${C_B}${C_G}" "$*" "${C_0}"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s[warn] %s%s\n' "${C_Y}" "$*" "${C_0}" >&2; }
die()  { printf '%s[error] %s%s\n' "${C_R}" "$*" "${C_0}" >&2; exit 1; }

usage() {
	cat <<'EOF'
build-msys2.sh -- build the sigrok stack for rdc2-sigrok from pinned git commits
(Windows, MSYS2 UCRT64 shell).

Usage: scripts/build-msys2.sh [OPTIONS]

Options:
  --prefix DIR     Install prefix. Default: $RDC2_SIGROK_PREFIX or ~/.local/rdc2-sigrok
                   (an MSYS2 path; ~ is C:\msys64\home\<user>)
  --only NAME      Build only this component; repeatable. One of:
                     libserialport  libsigrok  libsigrokdecode  sigrok-cli
                     pulseview
                   Default: all five, in dependency order.
  --clean          Discard build artefacts first: reset every selected source
                   tree to its pinned commit, drop untracked files, remove the
                   CMake build dir. Forces a full reconfigure and rebuild.
  --jobs N         Parallel make/ninja jobs. Default: number of CPUs.
  --no-pacman      Do not run "pacman -S"; assume the packages are already
                   present. Useful offline or on a managed machine.
  -h, --help       This text.

Environment:
  RDC2_SIGROK_PREFIX    Same as --prefix (the command line wins).

What it does:
  1. pacman -S of the build dependencies (unless --no-pacman).
  2. Clone/refresh each upstream repo into .build/src/<name> and reset it to
     the commit pinned in scripts/versions.env.
  3. Apply scripts/patches/<component>-*.patch, if any.
  4. Run <repo>/sigrok/apply.sh <libsigrok-src> to inject the out-of-tree
     driver, if that hook exists.
  5. Build and install into the prefix:
       libserialport    autotools, with the Windows patches
       libsigrok        autotools, --disable-python/java/ruby, C++ bindings on
       libsigrokdecode  autotools, embeds MSYS2's python
       sigrok-cli       autotools
       pulseview        CMake + Ninja, Qt6 from MSYS2, shared libraries
  6. Verify: every installed binary must import libsigrok/libsigrokcxx/
     libsigrokdecode DLLs that live in the prefix, and the demo driver must
     produce samples. The script fails if it does not.

No hardware is opened: the self-test only ever uses "-d demo".

After a successful build (in the same UCRT64 shell):
  . scripts/env.sh          # puts $PREFIX/bin on PATH
  sigrok-cli --version
EOF
}

#-----------------------------------------------------------------------------
# Argument parsing
#-----------------------------------------------------------------------------

while [ $# -gt 0 ]; do
	case "$1" in
	--prefix)    [ $# -ge 2 ] || die "--prefix needs an argument"; PREFIX="$2"; shift 2 ;;
	--prefix=*)  PREFIX="${1#*=}"; shift ;;
	--only)      [ $# -ge 2 ] || die "--only needs an argument"; COMPONENTS="${COMPONENTS} $2"; shift 2 ;;
	--only=*)    COMPONENTS="${COMPONENTS} ${1#*=}"; shift ;;
	--jobs)      [ $# -ge 2 ] || die "--jobs needs an argument"; JOBS="$2"; shift 2 ;;
	--jobs=*)    JOBS="${1#*=}"; shift ;;
	--clean)     CLEAN=1; shift ;;
	--no-pacman) DO_PACMAN=0; shift ;;
	-h|--help)   usage; exit 0 ;;
	*)           usage >&2; die "unknown option: $1" ;;
	esac
done

case "${JOBS}" in ''|*[!0-9]*) die "--jobs must be a positive integer" ;; esac
[ "${JOBS}" -ge 1 ] 2>/dev/null || die "--jobs must be >= 1"

[ -n "${COMPONENTS}" ] || COMPONENTS="${ALL_COMPONENTS}"
for c in ${COMPONENTS}; do
	case " ${ALL_COMPONENTS} " in
	*" ${c} "*) ;;
	*) die "unknown component '${c}' (expected one of: ${ALL_COMPONENTS})" ;;
	esac
done

# Absolutise the prefix without requiring it to exist yet.
case "${PREFIX}" in
/*) ;;
 *) PREFIX="$(pwd -P)/${PREFIX}" ;;
esac

selected() {
	case " ${COMPONENTS} " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

#-----------------------------------------------------------------------------
# Pinned revisions
#-----------------------------------------------------------------------------

[ -f "${SCRIPT_DIR}/versions.env" ] || die "missing ${SCRIPT_DIR}/versions.env"
# shellcheck source=versions.env
. "${SCRIPT_DIR}/versions.env"

repo_url() {
	case "$1" in
	libserialport)   printf '%s' "${LIBSERIALPORT_URL}" ;;
	libsigrok)       printf '%s' "${LIBSIGROK_URL}" ;;
	libsigrokdecode) printf '%s' "${LIBSIGROKDECODE_URL}" ;;
	sigrok-cli)      printf '%s' "${SIGROK_CLI_URL}" ;;
	pulseview)       printf '%s' "${PULSEVIEW_URL}" ;;
	esac
}
repo_commit() {
	case "$1" in
	libserialport)   printf '%s' "${LIBSERIALPORT_COMMIT}" ;;
	libsigrok)       printf '%s' "${LIBSIGROK_COMMIT}" ;;
	libsigrokdecode) printf '%s' "${LIBSIGROKDECODE_COMMIT}" ;;
	sigrok-cli)      printf '%s' "${SIGROK_CLI_COMMIT}" ;;
	pulseview)       printf '%s' "${PULSEVIEW_COMMIT}" ;;
	esac
}
repo_date() {
	case "$1" in
	libserialport)   printf '%s' "${LIBSERIALPORT_DATE}" ;;
	libsigrok)       printf '%s' "${LIBSIGROK_DATE}" ;;
	libsigrokdecode) printf '%s' "${LIBSIGROKDECODE_DATE}" ;;
	sigrok-cli)      printf '%s' "${SIGROK_CLI_DATE}" ;;
	pulseview)       printf '%s' "${PULSEVIEW_DATE}" ;;
	esac
}

#-----------------------------------------------------------------------------
# Toolchain environment
#-----------------------------------------------------------------------------

# The MSYS2 shell profile sets MSYSTEM, MINGW_PREFIX (/ucrt64) and
# MINGW_PACKAGE_PREFIX (mingw-w64-ucrt-x86_64) and puts the matching
# toolchain first on PATH.  MINGW64 works the same way with the msvcrt
# toolchain; the other environments (clang, 32-bit) are untested.
case "${MSYSTEM:-}" in
UCRT64|MINGW64) ;;
*) die "run this from an MSYS2 UCRT64 shell (MSYSTEM is '${MSYSTEM:-unset}')" ;;
esac
[ -n "${MINGW_PREFIX:-}" ] && [ -n "${MINGW_PACKAGE_PREFIX:-}" ] \
	|| die "MINGW_PREFIX/MINGW_PACKAGE_PREFIX are not set; use the MSYS2 login shell (bash -l)"

pacman_deps() {
	step "MSYS2 packages (${MSYSTEM})"
	local missing="" f
	for f in ${MSYS_DEPS}; do
		pacman -Qq "${f}" >/dev/null 2>&1 || missing="${missing} ${f}"
	done
	for f in ${MINGW_DEPS}; do
		pacman -Qq "${MINGW_PACKAGE_PREFIX}-${f}" >/dev/null 2>&1 \
			|| missing="${missing} ${MINGW_PACKAGE_PREFIX}-${f}"
	done
	if [ -z "${missing}" ]; then
		info "all present: ${MSYS_DEPS} + ${MINGW_PACKAGE_PREFIX}-{${MINGW_DEPS// /,}}"
		return 0
	fi
	if [ "${DO_PACMAN}" -eq 0 ]; then
		die "--no-pacman given but these packages are missing:${missing}"
	fi
	info "installing:${missing}"
	# shellcheck disable=SC2086
	pacman -S --needed --noconfirm ${missing}
}

setup_env() {
	# The prefix first: our libsigrok*.dll for the verification run, and our
	# .pc files ahead of anything a mingw-w64-*-libsigrok package would put
	# into $MINGW_PREFIX/lib/pkgconfig.  MSYS2 converts both lists to
	# Windows form when it launches the native toolchain.
	PATH="${PREFIX}/bin:${PATH}"
	export PATH
	XDG_DATA_DIRS="${PREFIX}/share${XDG_DATA_DIRS:+:${XDG_DATA_DIRS}}"
	export XDG_DATA_DIRS
	PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig:${MINGW_PREFIX}/lib/pkgconfig:${MINGW_PREFIX}/share/pkgconfig"
	export PKG_CONFIG_PATH

	# Native CMake wants Windows paths; ';' is its list separator.
	PREFIX_W="$(cygpath -m "${PREFIX}")"
	CMAKE_PREFIX_PATH="${PREFIX_W};$(cygpath -m "${MINGW_PREFIX}")"
	export CMAKE_PREFIX_PATH

	# Python is only a build tool here (libsigrok's enums.py generator) and
	# the interpreter libsigrokdecode embeds; the Python *bindings* are off.
	PYTHON="${MINGW_PREFIX}/bin/python3"
	export PYTHON
	[ -x "${PYTHON}" ] || die "missing ${PYTHON} (pacman -S ${MINGW_PACKAGE_PREFIX}-python)"

	# The stock libsigrok configure adds -lws2_32 itself; nothing else is
	# platform specific.  Keep configure/cmake from reaching into a user's
	# environment for flags meant for other builds.
	unset CFLAGS CXXFLAGS LDFLAGS CPPFLAGS || true

	mkdir -p "${SRC_DIR}" "${OBJ_DIR}" "${STAMP_DIR}" "${LOG_DIR}" "${PREFIX}"
}

#-----------------------------------------------------------------------------
# Source preparation (same logic as build-macos.sh)
#-----------------------------------------------------------------------------

tree_fingerprint() {
	local name="$1" p
	printf 'prefix=%s\n' "${PREFIX}"
	printf 'commit=%s\n' "$(repo_commit "${name}")"
	for p in "${PATCH_DIR}/${name}"-*.patch; do
		[ -f "${p}" ] || continue
		printf 'patch=%s %s\n' "$(basename "${p}")" "$(sha256sum "${p}" | cut -d' ' -f1)"
	done
	if [ "${name}" = "libsigrok" ]; then
		if [ -f "${DRIVER_HOOK}" ]; then
			printf 'driver=%s\n' "$(find "${REPO_ROOT}/sigrok" -type f \
				! -name '*.md' ! -name 'LICENSE' -print0 \
				| sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
		else
			printf 'driver=none\n'
		fi
	fi
}

apply_patches() {
	local name="$1" src="$2" p
	for p in "${PATCH_DIR}/${name}"-*.patch; do
		[ -f "${p}" ] || continue
		info "patch: $(basename "${p}")"
		git -C "${src}" apply --whitespace=nowarn "${p}" \
			|| die "failed to apply $(basename "${p}") to ${name}"
	done
}

run_driver_hook() {
	local src="$1"
	[ -f "${DRIVER_HOOK}" ] || return 0
	step "Injecting out-of-tree driver via sigrok/apply.sh"
	bash "${DRIVER_HOOK}" "${src}" || die "sigrok/apply.sh failed"
	info "driver hook done"
}

SRC_STATE=""
prepare_source() {
	local name="$1"
	local src="${SRC_DIR}/${name}"
	local url commit stamp want have
	url="$(repo_url "${name}")"
	commit="$(repo_commit "${name}")"
	stamp="${STAMP_DIR}/${name}.state"
	want="$(tree_fingerprint "${name}")"
	have=""
	if [ -f "${stamp}" ]; then have="$(cat "${stamp}")"; fi

	if [ ! -d "${src}/.git" ]; then
		rm -rf "${src}"
		# LF checkouts no matter what a global core.autocrlf says: the
		# patches are LF and autotools/CMake input must stay LF.
		git -c core.autocrlf=false clone --quiet "${url}" "${src}" \
			|| die "clone of ${url} failed"
		git -C "${src}" config core.autocrlf false
		have=""
	fi

	if [ "${CLEAN}" -eq 0 ] && [ -n "${have}" ] && [ "${have}" = "${want}" ]; then
		SRC_STATE="reused"
		return 0
	fi

	rm -f "${stamp}"
	if ! git -C "${src}" cat-file -e "${commit}^{commit}" 2>/dev/null; then
		info "fetching ${name}"
		git -C "${src}" fetch --quiet --tags origin || die "fetch of ${name} failed"
	fi
	git -C "${src}" reset --quiet --hard "${commit}" || die "cannot check out ${name} ${commit}"
	git -C "${src}" clean -qxdff
	apply_patches "${name}" "${src}"
	if [ "${name}" = "libsigrok" ]; then run_driver_hook "${src}"; fi
	printf '%s' "${want}" > "${stamp}"
	SRC_STATE="fresh"
}

#-----------------------------------------------------------------------------
# Builders
#-----------------------------------------------------------------------------

autotools_build() {
	local name="$1" state="$2"; shift 2
	local src="${SRC_DIR}/${name}"
	local log="${LOG_DIR}/${name}.log"

	if [ "${state}" = "fresh" ] || [ ! -f "${src}/configure" ]; then
		info "autogen.sh"
		( cd "${src}" && ./autogen.sh ) >>"${log}" 2>&1 \
			|| { tail -30 "${log}"; die "${name}: autogen.sh failed (see ${log})"; }
	fi
	if [ ! -f "${src}/config.status" ] || [ "${src}/configure" -nt "${src}/config.status" ]; then
		info "configure --prefix=${PREFIX} $*"
		( cd "${src}" && ./configure --prefix="${PREFIX}" "$@" ) >>"${log}" 2>&1 \
			|| { tail -40 "${log}"; die "${name}: configure failed (see ${log})"; }
	fi
	info "make -j${JOBS}"
	make -C "${src}" -j"${JOBS}" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "${name}: build failed (see ${log})"; }
	# install -C keeps the mtime of unchanged files, so that an unchanged
	# header does not make every dependent recompile on the next run.
	info "make install"
	make -C "${src}" install \
		INSTALL_DATA="/usr/bin/install -c -C -m 644" \
		INSTALL_HEADER="/usr/bin/install -c -C -m 644" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "${name}: install failed (see ${log})"; }
}

build_libserialport() {
	local state="$1"
	: > "${LOG_DIR}/libserialport.log"
	# Built from source, unlike on macOS: the release needs
	# scripts/patches/libserialport-0001-*.patch before it can report the
	# USB VID/PID of a port whose driver owns the whole device (usbser
	# bound by windows/rdc2-0064-usbser.inf), which is how the rdc2-sigrok
	# driver finds the board, and 0002/0003 to open the port without
	# control transfers the firmware cannot survive.
	autotools_build libserialport "${state}"
}

build_libsigrok() {
	local state="$1"
	: > "${LOG_DIR}/libsigrok.log"
	# C++ bindings (libsigrokcxx) stay on: PulseView needs them. They pull in
	# glibmm-2.4 and need doxygen + a python3 to generate enums.{cpp,hpp}.
	autotools_build libsigrok "${state}" \
		--disable-python --disable-java --disable-ruby --enable-cxx
	pkg-config --exists libsigrokcxx \
		|| die "libsigrokcxx.pc not installed -- C++ bindings did not build"
}

build_libsigrokdecode() {
	local state="$1"
	: > "${LOG_DIR}/libsigrokdecode.log"
	# PYTHON3 is the interpreter used by "make install" to byte-compile the
	# decoders; the embedded libpython comes from python3-embed.pc.
	autotools_build libsigrokdecode "${state}" "PYTHON3=${PYTHON}"
}

build_sigrok_cli() {
	local state="$1"
	: > "${LOG_DIR}/sigrok-cli.log"
	autotools_build sigrok-cli "${state}"
}

build_pulseview() {
	local state="$1"
	local src="${SRC_DIR}/pulseview"
	local bld="${OBJ_DIR}/pulseview"
	local log="${LOG_DIR}/pulseview.log"
	: > "${log}"

	if [ "${state}" = "fresh" ]; then rm -rf "${bld}"; fi
	mkdir -p "${bld}"

	# Qt5 is probed first by PulseView's CMakeLists and is simply absent
	# here, so Qt6 (>= 6.2 required) is what gets used.  STATIC_PKGDEPS_LIBS
	# is off because MSYS2 has no static glib/libsigrok (see the header).
	info "cmake configure"
	cmake -G Ninja -S "$(cygpath -m "${src}")" -B "$(cygpath -m "${bld}")" \
		-DCMAKE_BUILD_TYPE=RelWithDebInfo \
		-DCMAKE_INSTALL_PREFIX="${PREFIX_W}" \
		-DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}" \
		-DSTATIC_PKGDEPS_LIBS=FALSE \
		-DDISABLE_WERROR=TRUE \
		-DENABLE_DECODE=TRUE \
		-DENABLE_TESTS=FALSE \
		>>"${log}" 2>&1 || { tail -40 "${log}"; die "pulseview: cmake failed (see ${log})"; }

	info "cmake --build -j${JOBS}"
	cmake --build "$(cygpath -m "${bld}")" --parallel "${JOBS}" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "pulseview: build failed (see ${log})"; }
	info "cmake --install"
	cmake --install "$(cygpath -m "${bld}")" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "pulseview: install failed (see ${log})"; }
}

#-----------------------------------------------------------------------------
# Verification (demo driver only -- never touches real hardware)
#-----------------------------------------------------------------------------

# Windows resolves DLLs by name, first from the directory of the executable
# and then along PATH.  Every sigrok DLL a binary imports must therefore sit
# next to it in $PREFIX/bin, and nothing of the same name should shadow it
# from $MINGW_PREFIX/bin (where a pacman-installed libsigrok would live).
check_linkage() {
	local bin="$1" needed dll
	[ -x "${bin}" ] || die "expected ${bin} to exist"
	needed="$(objdump -p "${bin}" | awk '/DLL Name:/ {print $3}' \
		| grep -E '^libsigrok(cxx|decode)?-[0-9]+\.dll$' || true)"
	[ -n "${needed}" ] || die "$(basename "${bin}") imports no libsigrok DLL"
	for dll in ${needed}; do
		[ -f "${PREFIX}/bin/${dll}" ] \
			|| die "$(basename "${bin}") imports ${dll}, which is not in ${PREFIX}/bin"
		if [ -f "${MINGW_PREFIX}/bin/${dll}" ]; then
			warn "${MINGW_PREFIX}/bin/${dll} exists too (pacman libsigrok?); it loses"
			warn "against ${PREFIX}/bin next to the .exe but shadows ours elsewhere on PATH"
		fi
	done
	# shellcheck disable=SC2086
	info "$(basename "${bin}"): imports $(printf '%s ' ${needed})from ${PREFIX}/bin"
}

verify() {
	step "Verification"
	local cli="${PREFIX}/bin/sigrok-cli.exe"
	local pv="${PREFIX}/bin/pulseview.exe"

	if selected sigrok-cli || [ -x "${cli}" ]; then
		check_linkage "${cli}"
		info "sigrok-cli --version"
		"${cli}" --version | sed 's/^/      /'
		# -d demo: the demo driver is software-only. Never run a bare --scan.
		info "sigrok-cli -d demo --samples 100 -O ascii"
		"${cli}" -d demo --samples 100 -O ascii >/dev/null \
			|| die "demo capture failed"
		local pds srderr
		pds="$("${cli}" -L 2>/dev/null | sed -n '/Supported protocol decoders/,$p' \
			| tail -n +2 | grep -c . || true)"
		[ "${pds}" -gt 10 ] || die "sigrok-cli -L listed no protocol decoders"
		info "sigrok-cli -L: ${pds} protocol decoders"
		srderr="$("${cli}" -L 2>&1 >/dev/null | grep "Failed to load decoder" || true)"
		if [ -n "${srderr}" ]; then
			printf '%s\n' "${srderr}" >&2
			die "libsigrokdecode failed to load decoders"
		fi
	fi

	if selected pulseview || [ -x "${pv}" ]; then
		check_linkage "${pv}"
		# -D skips the scan-everything pass, -d demo restricts the one
		# explicit scan to the software-only demo driver, offscreen keeps
		# Qt windowless.  pulseview.exe is linked with -mwindows, so it
		# prints nothing on a console, but a pipe is a valid stdout for it.
		info "pulseview -V -D -d demo (offscreen, no device scan)"
		QT_QPA_PLATFORM=offscreen "${pv}" -V -D -d demo 2>/dev/null \
			| sed -n '1s/^/      /p' \
			|| die "pulseview -V failed"
	fi
}

#-----------------------------------------------------------------------------
# Main
#-----------------------------------------------------------------------------

START_TS="$(date +%s)"

step "sigrok stack + RDC2-0064 driver (MSYS2 ${MSYSTEM})"
info "prefix     ${PREFIX}"
info "components ${COMPONENTS}"
info "jobs       ${JOBS}"
if [ "${CLEAN}" -eq 1 ]; then info "clean      yes"; fi

pacman_deps
setup_env
info "PKG_CONFIG_PATH=${PKG_CONFIG_PATH}"

if selected libsigrok; then
	if [ -f "${DRIVER_HOOK}" ]; then
		info "driver hook ${DRIVER_HOOK}"
	else
		warn "no ${DRIVER_HOOK} yet -- building vanilla libsigrok without the rdc2-sigrok driver"
	fi
fi

for comp in ${ALL_COMPONENTS}; do
	selected "${comp}" || continue
	step "${comp} $(repo_commit "${comp}" | cut -c1-12) ($(repo_date "${comp}"))"
	prepare_source "${comp}"
	case "${comp}" in
	libserialport)   build_libserialport "${SRC_STATE}" ;;
	libsigrok)       build_libsigrok "${SRC_STATE}" ;;
	libsigrokdecode) build_libsigrokdecode "${SRC_STATE}" ;;
	sigrok-cli)      build_sigrok_cli "${SRC_STATE}" ;;
	pulseview)       build_pulseview "${SRC_STATE}" ;;
	esac
done

verify

ELAPSED=$(( $(date +%s) - START_TS ))
step "Done in $((ELAPSED / 60))m $((ELAPSED % 60))s"
info "binaries in ${PREFIX}/bin:"
for f in "${PREFIX}/bin"/*.exe; do [ -e "${f}" ] && info "  $(basename "${f}")"; done
info "run '. ${SCRIPT_DIR}/env.sh' in this shell to put them on PATH"
