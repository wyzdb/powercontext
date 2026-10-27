#!/usr/bin/env bash
# Check the Linux prerequisites for seekdb embedded mode and print a fallback
# if the native binding cannot be loaded.
set -euo pipefail

ok=1
arch="$(uname -m)"

if ! command -v node >/dev/null 2>&1; then
  echo "missing: node (need Node.js 20+)"
  ok=0
else
  echo "node: $(node -v)"
fi

if ! ldconfig -p 2>/dev/null | grep -q 'libaio.so.1'; then
  echo "missing: libaio.so.1"
  echo "  Ubuntu 22.04: sudo apt-get install -y libaio1"
  echo "  Ubuntu 24.04: sudo apt-get install -y libaio1t64"
  echo "  then: sudo ln -sf /usr/lib/${arch}-linux-gnu/libaio.so.1t64 /usr/lib/${arch}-linux-gnu/libaio.so.1"
  ok=0
else
  echo "libaio: ok"
fi

binding="$(find "${HOME}/.seekdb/bindings" -name 'libseekdb.so' 2>/dev/null | head -n 1 || true)"
if [[ -z "${binding}" ]]; then
  echo "binding: not downloaded yet"
  echo "  run: pnpm prepare:seekdb (or one pnpm dev, which pre-downloads it)"
else
  echo "binding: ${binding}"
  echo "embedded launcher sets LD_PRELOAD automatically (scripts/run-embedded.sh)"
fi

if [[ "${ok}" -eq 0 ]]; then
  echo
  echo "Fallback without embedded mode:"
  echo "  docker compose up -d"
  echo "  cp .env.example .env   # set SEEKDB_MODE=server"
  echo "  pnpm dev:server"
  exit 1
fi

echo "Linux prerequisites look OK."
