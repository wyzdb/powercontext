#!/usr/bin/env bash
# Start the BFF with seekdb embedded mode on Linux/macOS.
# Linux needs libaio.so.1 and, on some glibc builds, libseekdb.so preloaded
# before Node starts (otherwise dlopen fails with "cannot allocate memory in
# static TLS block"). This wrapper handles both.
set -euo pipefail
cd "$(dirname "$0")/.."

# WSL/Windows interop can put the Windows Node ahead of the Linux Node in PATH.
# Prefer the Linux toolchain when it is installed in the conventional location.
if [[ -d "${HOME}/.local/node22/bin" ]]; then
  export PATH="${HOME}/.local/node22/bin:${PATH}"
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  LIB="$(find "${HOME}/.seekdb/bindings" -name 'libseekdb.dylib' 2>/dev/null | head -n 1 || true)"
  if [[ -n "${LIB}" && -z "${DYLD_INSERT_LIBRARIES:-}" ]]; then
    export DYLD_INSERT_LIBRARIES="${LIB}"
  fi
else
  LIB="$(find "${HOME}/.seekdb/bindings" -name 'libseekdb.so' 2>/dev/null | head -n 1 || true)"
  if [[ -n "${LIB}" && -z "${LD_PRELOAD:-}" ]]; then
    export LD_PRELOAD="${LIB}"
  fi
fi

export SEEKDB_MODE="${SEEKDB_MODE:-embedded}"
export PORT="${PORT:-8787}"
exec node_modules/.bin/tsx server/index.ts
