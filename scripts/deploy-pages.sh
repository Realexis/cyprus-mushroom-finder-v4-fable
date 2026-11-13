#!/usr/bin/env bash
# Build the PUBLIC site and publish it to the gh-pages branch (GitHub Pages).
# The branch is replaced each time (one commit, no history bloat).
# Since 2026-11-12 the 250 m squares are public (user decision). Anything named
# "private" (future finds log, village notes) must never be part of web/dist.
#
# DEPLOY_SUBDIR=<name>: publish into that folder of the existing gh-pages instead, and keep
# everything else already there (no force push). Used for side-by-side copies, e.g.
#   DEPLOY_REMOTE=https://github.com/Realexis/cyprus-mushroom-finder-preview.git \
#   DEPLOY_SUBDIR=v4-fable bash scripts/deploy-pages.sh
set -euo pipefail
cd "$(dirname "$0")/../web"
npm run build
# Last safety net: refuse to publish anything private.
if find dist -iname "*private*" -o -iname "*finds*" | grep -q .; then
  echo "✗ private files found in dist — refusing to deploy"; exit 1
fi
REMOTE=${DEPLOY_REMOTE:-$(git -C .. remote get-url origin)}
NAME="$(git -C .. config user.name || echo deploy)"
MAIL="$(git -C .. config user.email || echo deploy@localhost)"
TMP=$(mktemp -d)
if [ -n "${DEPLOY_SUBDIR:-}" ]; then
  case "$DEPLOY_SUBDIR" in */*|.*|"") echo "✗ DEPLOY_SUBDIR must be a plain folder name"; exit 1;; esac
  git clone -q --depth 1 --branch gh-pages "$REMOTE" "$TMP"
  rm -rf "${TMP:?}/$DEPLOY_SUBDIR"
  mkdir "$TMP/$DEPLOY_SUBDIR"
  cp -R dist/. "$TMP/$DEPLOY_SUBDIR"
  cd "$TMP"
  git add -A
  git -c user.name="$NAME" -c user.email="$MAIL" commit -q -m "Deploy $DEPLOY_SUBDIR/ $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -q "$REMOTE" gh-pages
  cd - >/dev/null
  rm -rf "$TMP"
  echo "✓ deployed to gh-pages/$DEPLOY_SUBDIR (the rest of the site kept)"
  exit 0
fi
cp -R dist/. "$TMP"
touch "$TMP/.nojekyll"
cd "$TMP"
git init -q -b gh-pages
git add -A
git -c user.name="$NAME" -c user.email="$MAIL" commit -q -m "Deploy $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q -f "$REMOTE" gh-pages
rm -rf "$TMP"
echo "✓ deployed to gh-pages"
