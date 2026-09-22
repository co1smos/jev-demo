#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT"

[[ -f .env ]] || { printf 'Missing %s/.env; copy .env.example and fill it in.\n' "$ROOT" >&2; exit 1; }
chmod 600 .env
set -a
# shellcheck disable=SC1091
. ./.env
set +a

for name in TYPESAFE_API_KEY ALPACA_API_KEY ALPACA_API_SECRET; do
    [[ -n ${!name:-} ]] || { printf '%s is missing from .env\n' "$name" >&2; exit 1; }
done

if command -v npm >/dev/null 2>&1; then
    [[ -d node_modules ]] || npm ci
fi

pid=
cleanup() {
    trap - INT TERM EXIT
    if [[ -n ${pid:-} ]] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

python3 -m jev_demo &
pid=$!
printf 'JEV Simulator started (PID %s). Press Ctrl-C to stop.\n' "$pid"
wait "$pid"
