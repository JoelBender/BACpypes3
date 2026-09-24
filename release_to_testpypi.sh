#!/bin/bash
# ---------------------------------------------------------------------------
# release_to_testpypi.sh — build with uv and publish to Test PyPI.
#
# Symmetric to release_to_pypi.sh: sources credentials from
# ~/.uv-publish.testpypi.env, runs `uv build`, then
# `uv publish --index testpypi`. Test PyPI still uses username +
# password (not a token), so the env file exports UV_PUBLISH_USERNAME
# and UV_PUBLISH_PASSWORD.
#
# Prerequisites:
#   - uv installed and on PATH
#   - ~/.uv-publish.testpypi.env exists and contains
#     UV_PUBLISH_USERNAME and UV_PUBLISH_PASSWORD
#   - pyproject.toml has a [[tool.uv.index]] entry named "testpypi"
# ---------------------------------------------------------------------------

set -euo pipefail

CRED_FILE="${HOME}/.uv-publish.testpypi.env"

if [[ ! -r "$CRED_FILE" ]]; then
    echo "error: cannot read $CRED_FILE" >&2
    echo "hint:  create it with UV_PUBLISH_USERNAME and UV_PUBLISH_PASSWORD" >&2
    exit 1
fi

# Load the credential env vars into this shell. `set -a` marks every
# assignment made until `set +a` as exported, which is what `uv publish`
# reads (UV_PUBLISH_USERNAME, UV_PUBLISH_PASSWORD).
set -a
# shellcheck disable=SC1090
source "$CRED_FILE"
set +a

# Fresh build. `uv build` writes to ./dist/; wiping it first stops old
# artefacts from an earlier version being re-uploaded by accident.
rm -Rf dist build
uv build

echo
echo "This is what was built:"
ls -1 dist/
echo

read -r -p "Upload to Test PyPI? [y/n] " yesno || exit 1
case "$yesno" in
    y|Y)
        uv publish --index testpypi
        ;;
    n|N)
        echo "Skipped."
        ;;
    *)
        echo "exit..."
        exit 1
        ;;
esac
