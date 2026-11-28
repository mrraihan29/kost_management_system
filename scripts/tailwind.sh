#!/bin/sh
set -eu

VERSION="v4.3.5"
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
BIN_DIR="$ROOT/.bin"

case "$(uname -m)" in
  x86_64|amd64)
    ASSET="tailwindcss-linux-x64"
    EXPECTED_SHA256="e47695cee3f0d90623a91f3939b08bdee610eb5ad99340adff9d4145b284d6cc"
    ;;
  aarch64|arm64)
    ASSET="tailwindcss-linux-arm64"
    EXPECTED_SHA256="ffcd0d21dbd7c605dc12743ff0c0b47debc963c86b399674084c1c8f2c96ecad"
    ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

BIN_PATH="$BIN_DIR/$ASSET-$VERSION"
URL="https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/$ASSET"

mkdir -p "$BIN_DIR"
if [ ! -f "$BIN_PATH" ]; then
  TMP_PATH="$BIN_PATH.tmp"
  curl -fsSL "$URL" -o "$TMP_PATH"
  mv -f "$TMP_PATH" "$BIN_PATH"
fi

ACTUAL_SHA256="$(sha256sum "$BIN_PATH" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  rm -f "$BIN_PATH"
  echo "SHA-256 mismatch for $BIN_PATH (expected $EXPECTED_SHA256, got $ACTUAL_SHA256)" >&2
  exit 1
fi

chmod +x "$BIN_PATH"
exec "$BIN_PATH" -i "$ROOT/static/css/input.css" -o "$ROOT/static/css/app.css" --minify "$@"
