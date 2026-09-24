#!/bin/bash
# ---------------------------------------------------------------------------
# release_to_pypi.sh — build with uv and publish to PyPI.
#
# This is the uv-native replacement for the previous twine-based script.
# It is deliberately kept out of the repository (see .gitignore) because
# it names a credentials file in $HOME and is a personal workflow helper,
# not a distributed artefact.
#
# Prerequisites:
#   - uv installed and on PATH
#   - ~/.uv-publish.pypi.env exists and contains UV_PUBLISH_TOKEN
#   - pyproject.toml has a [[tool.uv.index]] entry named "pypi"
# ---------------------------------------------------------------------------

set -euo pipefail

CRED_FILE="${HOME}/.uv-publish.pypi.env"

if [[ ! -r "$CRED_FILE" ]]; then
    echo "error: cannot read $CRED_FILE" >&2
    echo "hint:  create it with UV_PUBLISH_TOKEN=<your pypi token>" >&2
    exit 1
fi

# Load the credential env vars into this shell. `set -a` marks every
# assignment made until `set +a` as exported, which is what `uv publish`
# reads (UV_PUBLISH_TOKEN, etc.).
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

read -r -p "Upload to PyPI? [y/n] " yesno || exit 1
case "$yesno" in
    y|Y)
        uv publish --index pypi
        ;;
    n|N)
        echo "Skipped."
        ;;
    *)
        echo "exit..."
        exit 1
        ;;
esac
