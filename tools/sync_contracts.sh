#!/usr/bin/env bash
set -euo pipefail

SENDER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTRACTS_REPO="${CONTRACTS_REPO:-$SENDER_DIR/../contracts}"

if [[ ! -d "$CONTRACTS_REPO/schemas" ]] || [[ ! -d "$CONTRACTS_REPO/examples" ]]; then
  echo "ERROR: Contracts repo not found at $CONTRACTS_REPO"
  echo "  Set CONTRACTS_REPO=/path/to/contracts and retry."
  exit 1
fi

mkdir -p "$SENDER_DIR/contracts/schemas" "$SENDER_DIR/contracts/examples"

cp -v "$CONTRACTS_REPO/schemas/envelope.schema.json"              "$SENDER_DIR/contracts/schemas/"
cp -v "$CONTRACTS_REPO/schemas/payload-gnss.schema.json"          "$SENDER_DIR/contracts/schemas/"
cp -v "$CONTRACTS_REPO/schemas/payload-rainfall.schema.json"      "$SENDER_DIR/contracts/schemas/"
cp -v "$CONTRACTS_REPO/schemas/payload-strain.schema.json"        "$SENDER_DIR/contracts/schemas/"
cp -v "$CONTRACTS_REPO/schemas/payload-soil-pressure.schema.json" "$SENDER_DIR/contracts/schemas/"
cp -v "$CONTRACTS_REPO/schemas/payload-deep-displacement.schema.json" "$SENDER_DIR/contracts/schemas/"

cp -v "$CONTRACTS_REPO/examples/gnss-shangtan.json"               "$SENDER_DIR/contracts/examples/"
cp -v "$CONTRACTS_REPO/examples/rainfall-shangtan.json"           "$SENDER_DIR/contracts/examples/"
cp -v "$CONTRACTS_REPO/examples/strain-shangtan.json"             "$SENDER_DIR/contracts/examples/"
cp -v "$CONTRACTS_REPO/examples/soil-pressure-shangtan.json"      "$SENDER_DIR/contracts/examples/"
cp -v "$CONTRACTS_REPO/examples/deep-displacement-lingzhan.json"  "$SENDER_DIR/contracts/examples/"

echo
echo "Done. Now commit the updated files in sender/contracts/."
