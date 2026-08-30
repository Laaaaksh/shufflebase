#!/usr/bin/env bash
# Converts the raw Playwright recording into the two assets the README embeds.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IN="$ROOT/docs/assets/demo-raw.webm"
MP4="$ROOT/docs/assets/demo.mp4"
GIF="$ROOT/docs/assets/demo.gif"
PALETTE_DIR="$(mktemp -d)"
PALETTE="$PALETTE_DIR/palette.png"

if [[ ! -f "$IN" ]]; then
  echo "missing $IN -- run record.js first" >&2
  exit 1
fi

ffmpeg -y -loglevel error -i "$IN" \
  -vf "scale=1280:-2" -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$MP4"

ffmpeg -y -loglevel error -i "$IN" \
  -vf "fps=12,scale=960:-2:flags=lanczos,palettegen=stats_mode=diff" "$PALETTE"

ffmpeg -y -loglevel error -i "$IN" -i "$PALETTE" \
  -filter_complex "fps=12,scale=960:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer" \
  "$GIF"

rm -rf "$PALETTE_DIR" "$IN"

echo "wrote:"
ls -la "$MP4" "$GIF"
