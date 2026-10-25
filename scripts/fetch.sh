#!/usr/bin/env bash
# Downloads every file the entries list into files/<sha256>: from its own release
# (<id>-<version>) once published, else from the `staging` prerelease, where the
# submission form uploads <sha256>.<extension>. Usage: scripts/fetch.sh [checkout]
# Needs `gh` (GH_TOKEN) and cargo-horizon-mod. FILES_FROM=<dir> reads <dir>/<file>
# instead, for a local trial.
set -euo pipefail
checkout="${1:-.}"
mkdir -p files
cargo horizon-mod registry list "$checkout" | while read -r sha id version file; do
  [ -f "files/$sha" ] && continue
  ext="${file##*.}"
  tmp="$(mktemp -d)"
  if [ -n "${FILES_FROM:-}" ]; then
    cp "$FILES_FROM/$file" "$tmp/$file"
  elif gh release download "$id-$version" --pattern "$file" --dir "$tmp" 2>/dev/null; then
    :
  elif gh release download staging --pattern "$sha.$ext" --dir "$tmp"; then
    mv "$tmp/$sha.$ext" "$tmp/$file"
  else
    echo "::error::$id $version: $file is neither in release $id-$version nor in staging as $sha.$ext"
    exit 1
  fi
  mv "$tmp/$file" "files/$sha"
  rmdir "$tmp"
done
