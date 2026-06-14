#!/usr/bin/env bash
# Daily health report for the data-analysis vertical.
# Appends a dated entry to docs/daily-report.md so morning review is one file.
#
# Install (macOS launchd, runs daily ~09:00):
#   cp scripts/com.openwebui.daily-report.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.openwebui.daily-report.plist
#
# Manual run (any time):
#   ./scripts/daily_report.sh
#
# Or via crontab:
#   0 9 * * *  cd /Users/istale/Documents/open-webui-based-project && ./scripts/daily_report.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="/Users/istale/Documents/New project/repos/open-webui/.venv/bin/python"
OUT="$REPO_ROOT/docs/daily-report.md"

cd "$REPO_ROOT/backend"
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a && . "$REPO_ROOT/.env" && set +a
fi

REPORT_JSON=$(PYTHONPATH=. "$PY" -m open_webui.utils.data_analysis.replay_cli --since-days 1 report 2>/dev/null)
REGRESSION_JSON=$(PYTHONPATH=. "$PY" -m open_webui.utils.data_analysis.replay_cli --since-days 7 regression 2>/dev/null || true)

{
  echo ""
  echo "## $(date '+%Y-%m-%d %H:%M')"
  echo ""
  echo "### Last 24h — analytics"
  echo '```json'
  echo "$REPORT_JSON"
  echo '```'
  echo ""
  echo "### Last 7d — regression"
  echo '```json'
  echo "$REGRESSION_JSON"
  echo '```'
} >> "$OUT"

echo "appended -> $OUT"
