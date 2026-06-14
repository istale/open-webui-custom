#!/usr/bin/env bash
# Run on the ONLINE machine before transferring to the offline one.
#
# Bundles everything the offline machine needs into a single tarball:
#   - the repo (as a git bundle, so history is preserved)
#   - all pip wheels for backend/requirements.txt
#   - this scripts/ directory (so the offline wizard runs from inside)
#
# Output: ./dist/offline-bundle-YYYYMMDD-<branch>.tar.gz
#
# On the offline machine: extract anywhere, cd in, run ./scripts/offline-setup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
SAFE_BRANCH="${BRANCH//\//-}"
DATE="$(date +%Y%m%d)"
STAGE="$(mktemp -d -t owui-offline-XXXX)"
OUT_DIR="$REPO_ROOT/dist"
OUT="$OUT_DIR/offline-bundle-${DATE}-${SAFE_BRANCH}.tar.gz"
mkdir -p "$OUT_DIR"

echo "[prep] staging at $STAGE"

# 1. git bundle (preserves history, smaller than a zip of .git)
echo "[prep] (1/3) creating git bundle ..."
git bundle create "$STAGE/repo.bundle" --all

# 2. download all wheels for the offline pip install
echo "[prep] (2/3) downloading wheels into vendor/ ..."
mkdir -p "$STAGE/vendor"
# Use the user's current python; the offline machine should match its minor version.
PY="${PY:-python3}"
"$PY" -m pip download \
    --dest "$STAGE/vendor" \
    --requirement backend/requirements.txt \
    --quiet
echo "[prep]   wheels collected: $(ls "$STAGE/vendor" | wc -l)"

# 3. include the install wizard + checklist + python version stamp
echo "[prep] (3/3) packaging ..."
cp scripts/offline-setup.sh "$STAGE/"
cp docs/offline-install.md "$STAGE/" 2>/dev/null || true
cp docs/offline-verification-checklist.md "$STAGE/" 2>/dev/null || true
"$PY" -c "import sys; print('%d.%d' % sys.version_info[:2])" > "$STAGE/PYTHON_VERSION"

tar -czf "$OUT" -C "$STAGE" .
rm -rf "$STAGE"

echo ""
echo "[prep] done -> $OUT"
echo "[prep] size: $(du -h "$OUT" | cut -f1)"
echo "[prep] python version stamped: $(tar -xzf "$OUT" -O ./PYTHON_VERSION)"
echo ""
echo "Transfer this single file to the offline machine, then:"
echo "  mkdir owui-offline && tar -xzf offline-bundle-*.tar.gz -C owui-offline"
echo "  cd owui-offline && git clone repo.bundle repo && cd repo"
echo "  ../scripts/offline-setup.sh    # or ./scripts/offline-setup.sh after running git checkout"
