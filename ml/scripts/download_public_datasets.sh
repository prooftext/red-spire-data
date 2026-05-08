#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/ml/raw"
mkdir -p "$RAW_DIR"

# These URLs are placeholders for public benchmark mirrors and may require manual acceptance.
# The script stores metadata and any downloaded archives under ml/raw.

CMU_URL="https://www.cs.cmu.edu/~keystroke/"
KEYRECS_URL="https://github.com/keyrecs/keyrecs-dataset"
LSIA_URL="https://huggingface.co/datasets"

cat > "$RAW_DIR/dataset_sources.json" <<EOF
{
  "cmu": {"url": "$CMU_URL", "status": "manual_or_scripted_download"},
  "keyrecs": {"url": "$KEYRECS_URL", "status": "manual_or_scripted_download"},
  "lsia": {"url": "$LSIA_URL", "status": "manual_or_scripted_download"}
}
EOF

echo "Wrote dataset source manifest to $RAW_DIR/dataset_sources.json"
echo "Place downloaded files under:"
echo "  $RAW_DIR/cmu/"
echo "  $RAW_DIR/keyrecs/"
echo "  $RAW_DIR/lsia/"
