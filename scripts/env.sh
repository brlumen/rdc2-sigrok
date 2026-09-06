# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
#
# Sourceable environment for the sigrok stack built by scripts/build-macos.sh.
#
#   . scripts/env.sh                     # default prefix ~/.local/openla
#   OPENLA_PREFIX=/opt/openla . scripts/env.sh    # matches --prefix /opt/openla
#
# Puts $OPENLA_PREFIX/bin ahead of Homebrew on PATH, so that "sigrok-cli" and
# "pulseview" are the ones built here and not the Homebrew bottles.
# PKG_CONFIG_PATH is set as well so that anything you compile against this
# stack picks up our libsigrok*.pc rather than Homebrew's libsigrok 0.5.2.
#
# Not executable on purpose: source it, do not run it.

OPENLA_PREFIX="${OPENLA_PREFIX:-$HOME/.local/openla}"
export OPENLA_PREFIX

case ":${PATH}:" in
	*":${OPENLA_PREFIX}/bin:"*) ;;
	*) PATH="${OPENLA_PREFIX}/bin:${PATH}"; export PATH ;;
esac

case ":${PKG_CONFIG_PATH-}:" in
	*":${OPENLA_PREFIX}/lib/pkgconfig:"*) ;;
	*) PKG_CONFIG_PATH="${OPENLA_PREFIX}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
	   export PKG_CONFIG_PATH ;;
esac

case ":${MANPATH-}:" in
	*":${OPENLA_PREFIX}/share/man:"*) ;;
	*) MANPATH="${OPENLA_PREFIX}/share/man${MANPATH:+:${MANPATH}}"; export MANPATH ;;
esac

# libsigrokdecode loads <dir>/libsigrokdecode/decoders for every XDG system
# data dir.  Homebrew's glib reports /opt/homebrew/share as one, so by default
# our sigrok-cli/PulseView would also load the decoders of the Homebrew
# libsigrokdecode 0.5.3 bottle -- among them three that upstream has removed or
# renamed and that log "Failed to load decoder" on every start.  Restore the
# plain XDG default so that the decoder set is exactly the installed one;
# $OPENLA_PREFIX/share is reached through the compiled-in paths instead.
# build-macos.sh uses the same value. Drop this block if you need Homebrew's
# GLib data dir in the same shell.
XDG_DATA_DIRS="/usr/local/share:/usr/share"
export XDG_DATA_DIRS
