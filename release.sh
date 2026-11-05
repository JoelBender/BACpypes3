#!/bin/bash
# ---------------------------------------------------------------------------
# release.sh — cut a new BACpypes3 release end-to-end.
#
# Usage: ./release.sh <new-version>          # e.g. ./release.sh 0.0.110
#
# What it does, in order:
#   1. Preflight (read-only): argument shape, clean tree, on `main`,
#      remote up-to-date, tag doesn't exist, new version > current,
#      publish credentials in place. Any failure aborts BEFORE any
#      mutation.
#   2. Bump __version__ in bacpypes3/__init__.py.
#   3. Commit that ("bump version to <version>").
#   4. Create lightweight tag v<version> (matches the 13 existing
#      tags; no annotated tags have ever been used).
#   5. Push commit + tag to origin.
#   6. exec into release_to_pypi.sh, which sources
#      ~/.uv-publish.pypi.env, runs `uv build`, prompts, and runs
#      `uv publish --index pypi`.
# ---------------------------------------------------------------------------

set -euo pipefail

INIT_FILE="bacpypes3/__init__.py"
PUBLISH_SCRIPT="./release_to_pypi.sh"
CRED_FILE="${HOME}/.uv-publish.pypi.env"

die() {
    echo "error: $*" >&2
    exit 1
}

usage() {
    echo "usage: $0 <new-version>" >&2
    echo "       version must be N.N.N (e.g. 0.0.110)" >&2
    exit 2
}

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------

[[ $# -eq 1 ]] || usage
NEW_VERSION="$1"

# Version shape: three dotted numeric components. Rejects "v0.0.110",
# "0.0.110-rc1", "0.0", etc.
[[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "version '$NEW_VERSION' must be N.N.N (e.g. 0.0.110)"

# Must be at the repo root — the paths below are all repo-relative.
[[ -f "$INIT_FILE" ]] \
    || die "$INIT_FILE not found; run from the repo root"
[[ -x "$PUBLISH_SCRIPT" ]] \
    || die "$PUBLISH_SCRIPT not found or not executable"

# Publish credentials exist. Cheap to check now; catches a config
# problem before we make any commits or tags. The publish script
# checks the same file, but by then we've already pushed the tag.
[[ -r "$CRED_FILE" ]] \
    || die "credentials file $CRED_FILE not readable (needed by $PUBLISH_SCRIPT)"

# On the default branch. A release from a feature branch is almost
# certainly a mistake.
current_branch=$(git rev-parse --abbrev-ref HEAD)
[[ "$current_branch" == "main" ]] \
    || die "not on main (currently on '$current_branch')"

# Clean working tree and index. A release should be reproducible from
# what is committed; a stray edit would silently ship or be lost.
git diff --quiet \
    || die "unstaged changes present; commit or stash them first"
git diff --cached --quiet \
    || die "staged changes present; commit or reset them first"

# Local branch must match origin/main exactly. If we are ahead, `git
# push` at step 5 would push commits the user hasn't reviewed as part
# of the release; if we are behind, we would tag a stale state.
echo "fetching origin/main and tags..."
git fetch --tags origin main >/dev/null
local_head=$(git rev-parse HEAD)
remote_head=$(git rev-parse origin/main)
[[ "$local_head" == "$remote_head" ]] \
    || die "local main ($local_head) differs from origin/main ($remote_head); push or rebase first"

# Tag must not already exist locally or remotely. `git fetch --tags`
# above pulled remote tags into the local ref namespace, so a local
# rev-parse also catches a tag that already lives on origin.
if git rev-parse --verify --quiet "refs/tags/v$NEW_VERSION" >/dev/null; then
    die "tag v$NEW_VERSION already exists"
fi

# Current version from __init__.py — the single source per CLAUDE.md.
current_version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$INIT_FILE")
[[ -n "$current_version" ]] \
    || die "could not read __version__ from $INIT_FILE"

# New version must be strictly greater than current. Reject equal and
# regressions. `sort -V` is version-aware; a plain `>` string compare
# would call "0.0.9" > "0.0.10".
if [[ "$NEW_VERSION" == "$current_version" ]]; then
    die "new version $NEW_VERSION equals current version"
fi
highest=$(printf '%s\n%s\n' "$current_version" "$NEW_VERSION" | sort -V | tail -1)
if [[ "$highest" != "$NEW_VERSION" ]]; then
    die "new version $NEW_VERSION is not greater than current $current_version"
fi

echo "current version: $current_version"
echo "new version:     $NEW_VERSION"
echo

# ---------------------------------------------------------------------------
# 2. Bump
# ---------------------------------------------------------------------------

sed -i 's/^__version__ = ".*"$/__version__ = "'"$NEW_VERSION"'"/' "$INIT_FILE"

# Verify the edit actually took. Catches a botched sed if the file
# format ever drifts (e.g. someone changes single-quote to double, or
# adds a comment on the same line).
if ! grep -Fxq "__version__ = \"$NEW_VERSION\"" "$INIT_FILE"; then
    die "sed did not update $INIT_FILE as expected; check the file"
fi

# ---------------------------------------------------------------------------
# 3-5. Commit, tag, push
# ---------------------------------------------------------------------------

git add "$INIT_FILE"
git commit -m "bump version to $NEW_VERSION"
git tag "v$NEW_VERSION"

echo
echo "pushing main and v$NEW_VERSION to origin..."
git push origin main
git push origin "v$NEW_VERSION"

# ---------------------------------------------------------------------------
# 6. Build + publish (hand off)
# ---------------------------------------------------------------------------

echo
echo "handing off to $PUBLISH_SCRIPT ..."
exec "$PUBLISH_SCRIPT"
