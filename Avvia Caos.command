#!/bin/zsh
set -eu
cd -- "$(dirname -- "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Caos richiede Python 3.10 o successivo. Installa Python e riprova.\n'
  read -r '?Premi Invio per chiudere.'
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  printf 'Caos richiede Python 3.10 o successivo. Aggiorna Python e riprova.\n'
  read -r '?Premi Invio per chiudere.'
  exit 1
fi
exec python3 server.py "$@"
