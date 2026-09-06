#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
#
# build-macos.sh -- reproducible build of the sigrok stack for OpenLA.
#
# Builds libsigrok + libsigrokdecode + sigrok-cli + PulseView from the upstream
# git commits pinned in scripts/versions.env into a private prefix, so that the
# result never collides with (and never links against) Homebrew's libsigrok.
#
# Out-of-tree driver injection
# ----------------------------
# If <repo>/sigrok/apply.sh exists it is executed as
#
#     sigrok/apply.sh <libsigrok-source-dir>
#
# after the libsigrok tree has been reset to the pinned commit and before
# autogen.sh runs.  The hook is expected to copy the driver into
# src/hardware/<driver>/ and to patch src/Makefile.am and configure.ac.  It does
# not have to be idempotent: the tree is always pristine when it is called.
# The hook's own content is hashed, so editing the driver forces a rebuild of
# libsigrok on the next run and nothing else.  If the hook is absent, vanilla
# libsigrok is built and a notice is printed.
#
# Layout
# ------
#   <repo>/.build/src/<name>      upstream checkouts (gitignored)
#   <repo>/.build/build/pulseview out-of-tree CMake build dir
#   <repo>/.build/stamps/         "what is currently checked out" markers
#   <repo>/.build/logs/<name>.log full build log per component
#   $PREFIX/{bin,lib,share}       install tree (default ~/.local/openla)
#
# Re-running is cheap: components whose pinned commit, patches and driver hook
# are unchanged only re-run make (a no-op) and make install.
#
# No hardware is touched at any point.  The self-test uses the demo driver only.

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

ALL_COMPONENTS="libsigrok libsigrokdecode sigrok-cli pulseview"

PREFIX="${OPENLA_PREFIX:-${HOME}/.local/openla}"
COMPONENTS=""
CLEAN=0
DO_BREW=1
JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"

# Homebrew formulae required to build the stack.  Kept in one place so that
# --no-brew users can install them by hand from this list.
BREW_DEPS="autoconf automake libtool pkgconf cmake glib libzip libserialport \
libusb libftdi hidapi glibmm@2.66 doxygen boost qt python@3.12"

# Homebrew python used for (a) libsigrok's C++ enum generator and (b) the
# CPython that libsigrokdecode embeds.  libsigrokdecode's configure.ac probes
# python-3.12-embed first and knows nothing newer, so python@3.12 is the newest
# interpreter it accepts deterministically; python@3.14 would only be found via
# the unversioned python3-embed fallback.
PY_FORMULA="python@3.12"
PY_VERSION="3.12"

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
build-macos.sh -- build the sigrok stack for OpenLA from pinned git commits.

Usage: scripts/build-macos.sh [OPTIONS]

Options:
  --prefix DIR     Install prefix. Default: $OPENLA_PREFIX or ~/.local/openla
  --only NAME      Build only this component; repeatable. One of:
                     libsigrok  libsigrokdecode  sigrok-cli  pulseview
                   Default: all four, in dependency order.
  --clean          Discard build artefacts first: reset every selected source
                   tree to its pinned commit, drop untracked files, remove the
                   CMake build dir. Forces a full reconfigure and rebuild.
  --jobs N         Parallel make/cmake jobs. Default: number of CPUs.
  --no-brew        Do not run "brew install"; assume the dependencies are
                   already present. Useful offline or on a managed machine.
  -h, --help       This text.

Environment:
  OPENLA_PREFIX    Same as --prefix (the command line wins).

What it does:
  1. brew install of the build dependencies (unless --no-brew).
  2. Clone/refresh each upstream repo into .build/src/<name> and reset it to
     the commit pinned in scripts/versions.env.
  3. Apply scripts/patches/<component>-*.patch, if any.
  4. Run <repo>/sigrok/apply.sh <libsigrok-src> to inject the out-of-tree
     driver, if that hook exists.
  5. Build and install into the prefix:
       libsigrok        autotools, --disable-python/java/ruby, C++ bindings on
       libsigrokdecode  autotools, embeds Homebrew python@3.12
       sigrok-cli       autotools
       pulseview        CMake, Qt6 from Homebrew
  6. Verify: every installed binary must resolve libsigrok/libsigrokcxx/
     libsigrokdecode from the prefix (otool -L) and not from Homebrew, and the
     demo driver must produce samples. The script fails if it does not.

No hardware is opened: the self-test only ever uses "-d demo".

After a successful build:
  . scripts/env.sh          # puts $PREFIX/bin on PATH
  sigrok-cli --version
EOF
}

#-----------------------------------------------------------------------------
# Argument parsing
#-----------------------------------------------------------------------------

while [ $# -gt 0 ]; do
	case "$1" in
	--prefix)   [ $# -ge 2 ] || die "--prefix needs an argument"; PREFIX="$2"; shift 2 ;;
	--prefix=*) PREFIX="${1#*=}"; shift ;;
	--only)     [ $# -ge 2 ] || die "--only needs an argument"; COMPONENTS="${COMPONENTS} $2"; shift 2 ;;
	--only=*)   COMPONENTS="${COMPONENTS} ${1#*=}"; shift ;;
	--jobs)     [ $# -ge 2 ] || die "--jobs needs an argument"; JOBS="$2"; shift 2 ;;
	--jobs=*)   JOBS="${1#*=}"; shift ;;
	--clean)    CLEAN=1; shift ;;
	--no-brew)  DO_BREW=0; shift ;;
	-h|--help)  usage; exit 0 ;;
	*)          usage >&2; die "unknown option: $1" ;;
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

# Per-component accessors (bash 3.2 on macOS has no associative arrays).
repo_url() {
	case "$1" in
	libsigrok)       printf '%s' "${LIBSIGROK_URL}" ;;
	libsigrokdecode) printf '%s' "${LIBSIGROKDECODE_URL}" ;;
	sigrok-cli)      printf '%s' "${SIGROK_CLI_URL}" ;;
	pulseview)       printf '%s' "${PULSEVIEW_URL}" ;;
	esac
}
repo_commit() {
	case "$1" in
	libsigrok)       printf '%s' "${LIBSIGROK_COMMIT}" ;;
	libsigrokdecode) printf '%s' "${LIBSIGROKDECODE_COMMIT}" ;;
	sigrok-cli)      printf '%s' "${SIGROK_CLI_COMMIT}" ;;
	pulseview)       printf '%s' "${PULSEVIEW_COMMIT}" ;;
	esac
}
repo_date() {
	case "$1" in
	libsigrok)       printf '%s' "${LIBSIGROK_DATE}" ;;
	libsigrokdecode) printf '%s' "${LIBSIGROKDECODE_DATE}" ;;
	sigrok-cli)      printf '%s' "${SIGROK_CLI_DATE}" ;;
	pulseview)       printf '%s' "${PULSEVIEW_DATE}" ;;
	esac
}

#-----------------------------------------------------------------------------
# Toolchain environment
#-----------------------------------------------------------------------------

command -v brew >/dev/null 2>&1 || die "Homebrew not found; install it from https://brew.sh"
BREW_PREFIX="$(brew --prefix)"

brew_deps() {
	step "Homebrew dependencies"
	local missing="" f
	for f in ${BREW_DEPS}; do
		if brew list --versions "${f}" >/dev/null 2>&1; then
			continue
		fi
		missing="${missing} ${f}"
	done
	if [ -z "${missing}" ]; then
		info "all present: ${BREW_DEPS}"
		return 0
	fi
	if [ "${DO_BREW}" -eq 0 ]; then
		die "--no-brew given but these formulae are missing:${missing}"
	fi
	info "installing:${missing}"
	# shellcheck disable=SC2086
	brew install ${missing}
}

setup_env() {
	local qt_prefix
	qt_prefix="$(brew --prefix qt)"

	# GNU libtoolize is installed as glibtoolize; autoreconf insists on the
	# unprefixed name, which Homebrew keeps in libtool's gnubin shim dir.
	PATH="${BREW_PREFIX}/opt/libtool/libexec/gnubin:${BREW_PREFIX}/opt/${PY_FORMULA}/bin:${BREW_PREFIX}/bin:${PATH}"
	export PATH

	# Order matters. The prefix comes first so that OUR libsigrok.pc,
	# libsigrokcxx.pc and libsigrokdecode.pc win over the ones Homebrew's
	# libsigrok 0.5.2 bottle installs into $BREW_PREFIX/lib/pkgconfig.
	# glibmm@2.66, libsigc++@2 and python@3.12 are keg-only, hence explicit.
	PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig"
	PKG_CONFIG_PATH="${PKG_CONFIG_PATH}:${BREW_PREFIX}/opt/glibmm@2.66/lib/pkgconfig"
	PKG_CONFIG_PATH="${PKG_CONFIG_PATH}:${BREW_PREFIX}/opt/libsigc++@2/lib/pkgconfig"
	PKG_CONFIG_PATH="${PKG_CONFIG_PATH}:${BREW_PREFIX}/opt/${PY_FORMULA}/lib/pkgconfig"
	PKG_CONFIG_PATH="${PKG_CONFIG_PATH}:${BREW_PREFIX}/lib/pkgconfig"
	PKG_CONFIG_PATH="${PKG_CONFIG_PATH}:${BREW_PREFIX}/share/pkgconfig"
	export PKG_CONFIG_PATH

	CMAKE_PREFIX_PATH="${PREFIX}:${qt_prefix}:${BREW_PREFIX}"
	export CMAKE_PREFIX_PATH

	# Python is only a build tool here (libsigrok's enums.py generator) and
	# the interpreter libsigrokdecode embeds; the Python *bindings* are off.
	PYTHON="${BREW_PREFIX}/opt/${PY_FORMULA}/bin/python${PY_VERSION}"
	export PYTHON
	[ -x "${PYTHON}" ] || die "missing ${PYTHON} (brew install ${PY_FORMULA})"

	# libsigrokdecode's srd_init() walks the XDG system data dirs and loads
	# every <dir>/libsigrokdecode/decoders it finds.  Homebrew's glib reports
	# $BREW_PREFIX/share as such a dir, so without this the freshly built
	# stack also pulls in the decoders of the Homebrew libsigrokdecode 0.5.3
	# bottle -- including three that upstream has since removed or renamed
	# and that then fail to load on every start.  Restoring the plain XDG
	# default makes the runtime as reproducible as the build; our own
	# decoders and firmware are found through libsigrok's/libsigrokdecode's
	# compiled-in $PREFIX/share paths, not through XDG.  env.sh does the same.
	XDG_DATA_DIRS="/usr/local/share:/usr/share"
	export XDG_DATA_DIRS

	# Keep configure/cmake from silently reaching into a user's environment.
	unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH LD_LIBRARY_PATH || true

	mkdir -p "${SRC_DIR}" "${OBJ_DIR}" "${STAMP_DIR}" "${LOG_DIR}" "${PREFIX}"
}

#-----------------------------------------------------------------------------
# Source preparation
#-----------------------------------------------------------------------------

# Hash of everything that can change the content of a source tree besides the
# pinned commit itself: this component's patches, plus the driver hook tree for
# libsigrok. Used as the stamp so that touching either forces a clean redo.
tree_fingerprint() {
	local name="$1" p
	printf 'prefix=%s\n' "${PREFIX}"
	printf 'commit=%s\n' "$(repo_commit "${name}")"
	for p in "${PATCH_DIR}/${name}"-*.patch; do
		[ -f "${p}" ] || continue
		printf 'patch=%s %s\n' "$(basename "${p}")" "$(shasum -a 256 "${p}" | cut -d' ' -f1)"
	done
	if [ "${name}" = "libsigrok" ]; then
		if [ -f "${DRIVER_HOOK}" ]; then
			# Hash everything the hook could feed into the build. Docs and
			# the licence are excluded so that editing them does not cost a
			# full libsigrok rebuild; everything else counts, because we do
			# not get to know how the hook is put together.
			printf 'driver=%s\n' "$(find "${REPO_ROOT}/sigrok" -type f \
				! -name '*.md' ! -name 'LICENSE' -print0 \
				| sort -z | xargs -0 shasum -a 256 | shasum -a 256 | cut -d' ' -f1)"
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
	# The "hook is missing" notice is printed once per run from main(), so that
	# it also shows up on runs that reuse an already prepared source tree.
	[ -f "${DRIVER_HOOK}" ] || return 0
	step "Injecting out-of-tree driver via sigrok/apply.sh"
	bash "${DRIVER_HOOK}" "${src}" || die "sigrok/apply.sh failed"
	info "driver hook done"
}

# prepare_source <name> -> sets SRC_STATE to "fresh" when the tree was rebuilt
# from scratch (and therefore needs autogen/reconfigure), "reused" otherwise.
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
		git clone --quiet "${url}" "${src}" || die "clone of ${url} failed"
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

# autotools_build <name> <state> [configure args...]
# In-tree build: that is the configuration upstream CI exercises, and --clean
# (or any fingerprint change) wipes the tree via git clean anyway.
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
	# install -C keeps the mtime of unchanged files. Without it every run
	# re-stamps the installed headers, and everything downstream (sigrok-cli,
	# all of PulseView) recompiles even though nothing changed.
	info "make install"
	make -C "${src}" install \
		INSTALL_DATA="/usr/bin/install -c -C -m 644" \
		INSTALL_HEADER="/usr/bin/install -c -C -m 644" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "${name}: install failed (see ${log})"; }
}

build_libsigrok() {
	local state="$1"
	: > "${LOG_DIR}/libsigrok.log"
	# C++ bindings (libsigrokcxx) stay on: PulseView needs them. They pull in
	# glibmm-2.4 (Homebrew glibmm@2.66) and need doxygen + a python3 to
	# generate enums.{cpp,hpp} from the doxygen XML.
	autotools_build libsigrok "${state}" \
		--disable-python --disable-java --disable-ruby --enable-cxx
	pkg-config --exists libsigrokcxx \
		|| die "libsigrokcxx.pc not installed -- C++ bindings did not build"
}

build_libsigrokdecode() {
	local state="$1"
	: > "${LOG_DIR}/libsigrokdecode.log"
	# PYTHON3 is the interpreter used by "make install" to byte-compile the
	# decoders; the embedded libpython comes from python-3.12-embed.pc.
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

	# Qt5 is probed first by PulseView's CMakeLists and is simply absent here,
	# so Qt6 (Homebrew "qt", >= 6.2 required) is what gets used.
	# CMAKE_INSTALL_RPATH + BUILD_WITH_INSTALL_RPATH make the installed binary
	# find $PREFIX/lib without DYLD_LIBRARY_PATH.
	info "cmake configure"
	cmake -S "${src}" -B "${bld}" \
		-DCMAKE_BUILD_TYPE=RelWithDebInfo \
		-DCMAKE_INSTALL_PREFIX="${PREFIX}" \
		-DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}" \
		-DCMAKE_INSTALL_RPATH="${PREFIX}/lib" \
		-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
		-DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON \
		-DDISABLE_WERROR=TRUE \
		-DENABLE_DECODE=TRUE \
		-DENABLE_TESTS=FALSE \
		>>"${log}" 2>&1 || { tail -40 "${log}"; die "pulseview: cmake failed (see ${log})"; }

	info "cmake --build -j${JOBS}"
	cmake --build "${bld}" --parallel "${JOBS}" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "pulseview: build failed (see ${log})"; }
	info "cmake --install"
	cmake --install "${bld}" >>"${log}" 2>&1 \
		|| { tail -40 "${log}"; die "pulseview: install failed (see ${log})"; }
}

#-----------------------------------------------------------------------------
# Verification (demo driver only -- never touches real hardware)
#-----------------------------------------------------------------------------

# Fail if a binary resolves any sigrok library from outside the prefix, which
# is exactly what would happen if Homebrew's libsigrok 0.5.2 got picked up.
check_linkage() {
	local bin="$1" foreign ours
	[ -x "${bin}" ] || die "expected ${bin} to exist"
	foreign="$(otool -L "${bin}" | tail -n +2 | awk '{print $1}' \
		| grep -E '/libsigrok(cxx|decode)?[.0-9]*\.dylib$' \
		| grep -v "^${PREFIX}/" || true)"
	if [ -n "${foreign}" ]; then
		printf '%s\n' "${foreign}" >&2
		warn "$(basename "${bin}") links the Homebrew sigrok bottles instead of"
		warn "the ones in ${PREFIX}. Usually this means the component providing"
		warn "that library was skipped by --only; build the whole stack, or add"
		warn "--clean so the dependent is reconfigured against the prefix."
		die "$(basename "${bin}") links a sigrok library from outside ${PREFIX}"
	fi
	ours="$(otool -L "${bin}" | tail -n +2 | awk '{print $1}' \
		| grep -c "^${PREFIX}/lib/libsigrok" || true)"
	[ "${ours}" -ge 1 ] || die "$(basename "${bin}") does not link ${PREFIX}/lib/libsigrok*"
	info "$(basename "${bin}"): sigrok libs resolved from ${PREFIX}/lib"
}

verify() {
	step "Verification"
	local cli="${PREFIX}/bin/sigrok-cli"
	local pv="${PREFIX}/bin/pulseview"

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
			die "libsigrokdecode failed to load decoders (stale decoders on the search path?)"
		fi
	fi

	if selected pulseview || [ -x "${pv}" ]; then
		check_linkage "${pv}"
		info "pulseview -V -D -d demo (offscreen, no device scan)"
		# -D disables the scan-everything pass; -d demo restricts the single
		# explicit scan to the software-only demo driver. offscreen keeps Qt
		# from opening a window.
		QT_QPA_PLATFORM=offscreen "${pv}" -V -D -d demo 2>/dev/null | sed 's/^/      /' \
			|| die "pulseview --version failed"
	fi
}

#-----------------------------------------------------------------------------
# Main
#-----------------------------------------------------------------------------

START_TS="$(date +%s)"

step "OpenLA sigrok stack"
info "prefix     ${PREFIX}"
info "components ${COMPONENTS}"
info "jobs       ${JOBS}"
if [ "${CLEAN}" -eq 1 ]; then info "clean      yes"; fi

brew_deps
setup_env
info "PKG_CONFIG_PATH=${PKG_CONFIG_PATH}"

if selected libsigrok; then
	if [ -f "${DRIVER_HOOK}" ]; then
		info "driver hook ${DRIVER_HOOK}"
	else
		warn "no ${DRIVER_HOOK} yet -- building vanilla libsigrok without the OpenLA driver"
	fi
fi

for comp in ${ALL_COMPONENTS}; do
	selected "${comp}" || continue
	step "${comp} $(repo_commit "${comp}" | cut -c1-12) ($(repo_date "${comp}"))"
	prepare_source "${comp}"
	case "${comp}" in
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
ls -1 "${PREFIX}/bin" 2>/dev/null | sed 's/^/      /'
info "run '. ${SCRIPT_DIR}/env.sh' to put them on PATH"
