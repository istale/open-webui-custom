"""Version stamps for interaction-replay (Phase 1).

Kept dependency-free so the event logger can import it without pulling the tool
registration machinery. Bump these when the corresponding contract changes so
stored trajectories can be attributed to a specific config version.
"""

from __future__ import annotations

# Bump when the tool signatures / behavior change in a way that affects how the
# model is expected to call them.
TOOL_SPEC_VERSION = 'da-tools-2026-05-27'
