#!/bin/zsh
set -eu
cd "$(dirname "$0")/../.."
mobile_python="$(cat .mobile-ltz-runtime/python-path)"
exec "$mobile_python" tools/mobile-ltz/service.py "${1:-start}"
