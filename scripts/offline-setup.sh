#!/usr/bin/env bash
# Offline setup wizard — run inside the repo on the OFFLINE machine.
#
# Idempotent: re-run any time to update / verify.
#
# What it does, in order:
#   1. checks python (3.11 or 3.12)
#   2. creates .venv if missing
#   3. installs backend deps — prefers ../vendor/ (from offline-prep) if present,
#      otherwise tries pip (will fail cleanly on truly air-gapped machines)
#   4. installs the project editable (pip install -e backend --no-deps)
#   5. seeds .env from .env.example if .env doesn't exist
#   6. runs the data_analysis test suite as a smoke test
#   7. prints the next-step commands

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
VENV="$REPO_ROOT/.venv"
VENDOR="$(cd "$REPO_ROOT/.." && pwd)/vendor"  # offline-prep places it one level up
PIP_OPTS=()

echo "[setup] repo: $REPO_ROOT"
echo "[setup] (1/7) checking python ..."
# Prefer python3.12, then 3.11.
PY=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ver="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if [[ "$ver" == "3.12" || "$ver" == "3.11" ]]; then
      PY="$candidate"
      echo "[setup]   using $candidate (python $ver)"
      break
    fi
  fi
done
if [[ -z "$PY" ]]; then
  echo "[setup] ERROR: need python 3.11 or 3.12 — none found." >&2
  exit 1
fi

echo "[setup] (2/7) ensuring venv at $VENV ..."
if [[ ! -d "$VENV" ]]; then
  "$PY" -m venv "$VENV"
  echo "[setup]   venv created"
else
  echo "[setup]   venv exists, reusing"
fi
VPY="$VENV/bin/python"

if [[ -d "$VENDOR" ]]; then
  echo "[setup] (3/7) installing deps from $VENDOR (air-gapped mode) ..."
  PIP_OPTS=(--no-index --find-links "$VENDOR")
else
  echo "[setup] (3/7) no vendor/ dir found — falling back to PyPI"
  echo "[setup]   (if this machine has no internet, run offline-prep.sh on an online machine first)"
fi
"$VPY" -m pip install --quiet --upgrade pip "${PIP_OPTS[@]}" 2>/dev/null || \
  "$VPY" -m pip install --upgrade pip "${PIP_OPTS[@]}"
"$VPY" -m pip install --quiet -r backend/requirements.txt "${PIP_OPTS[@]}"
"$VPY" -m pip install --quiet pytest "${PIP_OPTS[@]}" || true  # pytest needed for smoke test

echo "[setup] (4/7) installing project editable ..."
"$VPY" -m pip install --quiet -e backend --no-deps

echo "[setup] (5/7) checking .env ..."
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "[setup]   seeded .env from .env.example — edit it before running eval"
  else
    cat > .env <<'EOF'
# Required for `replay_cli eval` (live LLM). Other commands work without these.
MINIMAX_BASE_URL=
MINIMAX_API_KEY=
MINIMAX_MODEL=
EOF
    echo "[setup]   created skeleton .env — fill in MINIMAX_* if you want to run eval"
  fi
else
  echo "[setup]   .env already present"
fi

echo "[setup] (6/7) smoke test — pytest tests/data_analysis/ ..."
"$VPY" -m pytest tests/data_analysis/ -q 2>&1 | tail -3

echo ""
echo "[setup] (7/7) ✅ ready. Next steps:"
cat <<EOF

  # Activate the venv for this shell:
  source "$VENV/bin/activate"

  # Run the offline-verification checklist:
  cd "$REPO_ROOT/backend"
  set -a && . ../.env && set +a && export PYTHONPATH=.
  CLI="python -m open_webui.utils.data_analysis.replay_cli"

  \$CLI --since-days 30 report
  \$CLI --since-days 30 intents --top 20
  \$CLI --since-days 30 satisfaction
  \$CLI --since-days 30 fit
  \$CLI --since-days 30 regression
  # \$CLI --since-days 30 eval    # needs MINIMAX_* in .env + network to the LLM

  # Full checklist with fill-in fields:
  open "$REPO_ROOT/docs/offline-verification-checklist.md"
EOF
