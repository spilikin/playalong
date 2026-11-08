#!/usr/bin/env bash
# Builds and signs the app, publishes it as release app-v<version>, and points the updater at it.
#
#   app/scripts/release.sh ["what's new"]
#
# Bump "version" in app/src-tauri/tauri.conf.json first; a version that's already released is refused.
# The signing key is ~/.tauri/playalong.key; its password lives in the login Keychain
# (service playalong-updater-key). Losing either means installed apps can't take updates any more.
set -euo pipefail

repo=spilikin/playalong
updates=updates
app=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "$app/.." && pwd)

version=$(jq -r .version "$app/src-tauri/tauri.conf.json")
tag="app-v$version"
notes=${1:-"Playalong $version"}
commit=$(git -C "$root" rev-parse HEAD)

[ -z "$(git -C "$root" status --porcelain)" ] || { echo "Commit or stash your changes first" >&2; exit 1; }
[ -n "$(git -C "$root" branch -r --contains "$commit")" ] || { echo "Commit $commit isn't pushed; push it first" >&2; exit 1; }
if gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
  echo "$tag is already released; bump the version in tauri.conf.json" >&2
  exit 1
fi

export TAURI_SIGNING_PRIVATE_KEY="$HOME/.tauri/playalong.key"
TAURI_SIGNING_PRIVATE_KEY_PASSWORD=$(security find-generic-password -s playalong-updater-key -w)
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD
(cd "$app" && ui/node_modules/.bin/tauri build)

bundle="$app/target/release/bundle/macos"
# A bundle whose signature doesn't verify opens as "damaged" once downloaded, with no way past it.
codesign --verify --deep --strict "$bundle/Playalong.app"
out="$app/target/release/publish"
rm -rf "$out" && mkdir -p "$out"
# The updater takes the .tar.gz; people downloading the app by hand get a zip, which Finder opens.
cp "$bundle/Playalong.app.tar.gz" "$out/Playalong-$version-arm64.app.tar.gz"
ditto -c -k --keepParent "$bundle/Playalong.app" "$out/Playalong-$version-arm64.zip"

jq -n \
  --arg version "$version" \
  --arg notes "$notes" \
  --arg date "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg signature "$(cat "$bundle/Playalong.app.tar.gz.sig")" \
  --arg url "https://github.com/$repo/releases/download/$tag/Playalong-$version-arm64.app.tar.gz" \
  '{version: $version, notes: $notes, pub_date: $date,
    platforms: {"darwin-aarch64": {signature: $signature, url: $url}}}' >"$out/latest.json"

gh release create "$tag" "$out/Playalong-$version-arm64.zip" "$out/Playalong-$version-arm64.app.tar.gz" \
  --repo "$repo" --target "$commit" --latest --title "Playalong $version" --notes "$notes"
if gh release view "$updates" --repo "$repo" >/dev/null 2>&1; then
  gh release upload "$updates" "$out/latest.json" --repo "$repo" --clobber
else
  gh release create "$updates" "$out/latest.json" --repo "$repo" --target "$commit" --latest=false \
    --title "Updates" --notes "What the app checks for updates: manifest.json (runtime) and latest.json (app)."
fi
echo "Published $tag; updater feed at https://github.com/$repo/releases/download/$updates/latest.json"
