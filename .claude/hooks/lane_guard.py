#!/usr/bin/env python3
"""PreToolUse hook: keep a lane's Claude instance inside the folders it owns.

A worktree created by scripts/worktrees.sh has a `.lane` file at its root
containing the lane name. Without that file (the lead checkout on main) every
edit is allowed. See docs/PARALLEL.md for the ownership table.
"""

import json
import os
import sys
from pathlib import Path

LANE_PATHS = {
    "hub": ["hub/"],
    "sim": ["sim/"],
    "web": ["web/"],
    "fw": ["firmware/", "fpga/"],
}


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    lane_file = root / ".lane"
    if not lane_file.is_file():
        return 0
    lane = lane_file.read_text().strip()
    allowed = LANE_PATHS.get(lane)
    if allowed is None:
        print(f"lane_guard: unknown lane '{lane}' in {lane_file}", file=sys.stderr)
        return 2

    tool_input = json.load(sys.stdin).get("tool_input", {})
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return 0
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return 0  # outside the repo (scratch files, memory): not this guard's business

    if any(rel.startswith(prefix) for prefix in allowed):
        return 0
    print(
        f"lane_guard: the '{lane}' lane may only edit {', '.join(allowed)} "
        f"(tried {rel}). Contract, docs, and build files belong to the lead on main: "
        "stop and report what needs to change. See docs/PARALLEL.md.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
