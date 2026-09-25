# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
#
# Sourceable environment for the sigrok stack built by scripts/build-macos.sh
# or, in an MSYS2 UCRT64 shell, scripts/build-msys2.sh.
#
#   . scripts/env.sh                     # default prefix ~/.local/rdc2-sigrok
#   RDC2_SIGROK_PREFIX=/opt/rdc2-sigrok . scripts/env.sh    # matches --prefix /opt/rdc2-sigrok
#
# Puts $RDC2_SIGROK_PREFIX/bin ahead of Homebrew (or /ucrt64) on PATH, so that
# "sigrok-cli" and "pulseview" are the ones built here and not the packaged
# ones.  PKG_CONFIG_PATH is set as well so that anything you compile against
# this stack picks up our libsigrok*.pc rather than a packaged libsigrok.
#
# Not executable on purpose: source it, do not run it.

RDC2_SIGROK_PREFIX="${RDC2_SIGROK_PREFIX:-$HOME/.local/rdc2-sigrok}"
export RDC2_SIGROK_PREFIX

case ":${PATH}:" in
	*":${RDC2_SIGROK_PREFIX}/bin:"*) ;;
	*) PATH="${RDC2_SIGROK_PREFIX}/bin:${PATH}"; export PATH ;;
esac

case ":${PKG_CONFIG_PATH-}:" in
	*":${RDC2_SIGROK_PREFIX}/lib/pkgconfig:"*) ;;
	*) PKG_CONFIG_PATH="${RDC2_SIGROK_PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
	   export PKG_CONFIG_PATH ;;
esac

case ":${MANPATH-}:" in
	*":${RDC2_SIGROK_PREFIX}/share/man:"*) ;;
	*) MANPATH="${RDC2_SIGROK_PREFIX}/share/man${MANPATH:+:${MANPATH}}"; export MANPATH ;;
esac

# libsigrokdecode loads <dir>/libsigrokdecode/decoders for every XDG system
# data dir.  Homebrew's glib reports /opt/homebrew/share as one, so by default
# our sigrok-cli/PulseView would also load the decoders of the Homebrew
# libsigrokdecode 0.5.3 bottle -- among them three that upstream has removed or
# renamed and that log "Failed to load decoder" on every start.  Restore the
# plain XDG default so that the decoder set is exactly the installed one;
# $RDC2_SIGROK_PREFIX/share is reached through the compiled-in paths instead.
# build-macos.sh uses the same value. Drop this block if you need Homebrew's
# GLib data dir in the same shell.
#
# MSYS2 has the opposite problem: its profile exports XDG_DATA_DIRS for
# bash-completion, and as soon as that variable exists GLib on Windows stops
# deriving the data dirs from the DLL location ($RDC2_SIGROK_PREFIX/share, where
# our decoders are).  Put the prefix in front instead of replacing the list,
# so that completion keeps working.  Outside an MSYS2 shell the variable is
# unset and the DLL-derived path is found without help.
case "$(uname -s)" in
Darwin)
	XDG_DATA_DIRS="/usr/local/share:/usr/share"
	export XDG_DATA_DIRS ;;
MSYS*|MINGW*)
	case ":${XDG_DATA_DIRS-}:" in
		*":${RDC2_SIGROK_PREFIX}/share:"*) ;;
		*) XDG_DATA_DIRS="${RDC2_SIGROK_PREFIX}/share${XDG_DATA_DIRS:+:${XDG_DATA_DIRS}}"
		   export XDG_DATA_DIRS ;;
	esac ;;
esac
