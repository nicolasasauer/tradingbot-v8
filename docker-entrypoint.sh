#!/usr/bin/env bash
# docker-entrypoint.sh
#
# Handles two deployment scenarios:
#   1. Fresh deployment (only docker-compose.yml present, ./user_data is empty)
#      → copies the bundled defaults into the empty volume so the bot can start.
#   2. Existing deployment (./user_data already populated by the user)
#      → leaves the user's files untouched and starts normally.

set -e

DEFAULTS_DIR="/freqtrade/user_data_defaults"
USER_DATA_DIR="/freqtrade/user_data"

if [ ! -f "${USER_DATA_DIR}/config.json" ]; then
    echo "==> No config.json found in user_data – copying bundled defaults..."
    mkdir -p "${USER_DATA_DIR}"
    # -n (no-clobber) preserves any files the user already has in the directory
    # (e.g. custom strategies or logs) while still adding missing default files.
    cp -rn "${DEFAULTS_DIR}/." "${USER_DATA_DIR}/"
    echo "==> Default configuration installed."
    echo "==> Edit ${USER_DATA_DIR}/config.json to customize exchange keys, password, etc."
fi

exec freqtrade "$@"
