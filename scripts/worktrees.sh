#!/usr/bin/env bash
# Lane worktrees for parallel Claude instances. See docs/PARALLEL.md.
#
#   scripts/worktrees.sh up [lane...]   create worktrees (default: hub sim web)
#   scripts/worktrees.sh status         worktrees and ahead/behind vs main
#   scripts/worktrees.sh merge          (lead, on main) merge lanes in order, testing between
#   scripts/worktrees.sh down [lane...] remove worktrees (branches are kept)
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
NAME="$(basename "$ROOT")"
PARENT="$(dirname "$ROOT")"
ALL_LANES=(hub sim web fw)
DEFAULT_LANES=(hub sim web)
MERGE_ORDER=(sim hub web fw)

lane_dir() { echo "$PARENT/$NAME-$1"; }

lane_port() {
  case "$1" in
    hub) echo 8001 ;; sim) echo 8002 ;; web) echo 8003 ;; fw) echo 8004 ;;
  esac
}

lane_pump() {
  case "$1" in
    fw) echo pump-001 ;;  # must match firmware/include/config.h
    *) echo "pump-$1" ;;
  esac
}

check_lane() {
  local l
  for l in "${ALL_LANES[@]}"; do [[ "$l" == "$1" ]] && return 0; done
  echo "unknown lane '$1' (expected one of: ${ALL_LANES[*]})" >&2
  exit 1
}

cmd_up() {
  local lanes=("$@") lane dir
  [[ ${#lanes[@]} -eq 0 ]] && lanes=("${DEFAULT_LANES[@]}")
  for lane in "${lanes[@]}"; do
    check_lane "$lane"
    dir="$(lane_dir "$lane")"
    if [[ -d "$dir" ]]; then
      echo "= $lane: $dir already exists"
      continue
    fi
    git -C "$ROOT" show-ref --verify --quiet "refs/heads/lane/$lane" \
      || git -C "$ROOT" branch "lane/$lane" main
    git -C "$ROOT" worktree add "$dir" "lane/$lane"
    echo "$lane" > "$dir/.lane"
    sed -e "s/^HUB_PORT=.*/HUB_PORT=$(lane_port "$lane")/" \
        -e "s/^PUMP_ID=.*/PUMP_ID=$(lane_pump "$lane")/" \
        "$ROOT/.env.example" > "$dir/.env"
    echo "+ $lane: $dir (branch lane/$lane, HUB_PORT=$(lane_port "$lane"), PUMP_ID=$(lane_pump "$lane"))"
  done
  echo
  echo "Next, per lane:  cd <worktree> && make setup && claude   then paste the lane brief from docs/PARALLEL.md"
}

cmd_status() {
  local lane counts
  git -C "$ROOT" worktree list
  echo
  for lane in "${ALL_LANES[@]}"; do
    if git -C "$ROOT" show-ref --verify --quiet "refs/heads/lane/$lane"; then
      counts="$(git -C "$ROOT" rev-list --left-right --count "main...lane/$lane")"
      echo "lane/$lane: behind main ${counts%%[[:space:]]*}, ahead ${counts##*[[:space:]]}"
    fi
  done
}

cmd_merge() {
  local branch lane
  branch="$(git -C "$ROOT" symbolic-ref --short HEAD)"
  [[ "$branch" == "main" ]] || { echo "run merge from the lead checkout on main (on $branch)" >&2; exit 1; }
  [[ -z "$(git -C "$ROOT" status --porcelain)" ]] || { echo "working tree not clean" >&2; exit 1; }
  for lane in "${MERGE_ORDER[@]}"; do
    git -C "$ROOT" show-ref --verify --quiet "refs/heads/lane/$lane" || continue
    if [[ -z "$(git -C "$ROOT" rev-list "main..lane/$lane")" ]]; then
      echo "= lane/$lane: nothing to merge"
      continue
    fi
    echo "+ merging lane/$lane"
    git -C "$ROOT" merge --no-ff "lane/$lane" -m "Merge lane/$lane"
    (cd "$ROOT" && make test) || { echo "tests failed after lane/$lane: fix on main or revert the merge" >&2; exit 1; }
  done
  echo
  echo "Merged. Now: run safety-reviewer on the combined diff, do the PLAN phase check, tick PLAN.md, git push."
}

cmd_down() {
  local lanes=("$@") lane dir
  [[ ${#lanes[@]} -eq 0 ]] && lanes=("${ALL_LANES[@]}")
  for lane in "${lanes[@]}"; do
    check_lane "$lane"
    dir="$(lane_dir "$lane")"
    [[ -d "$dir" ]] || continue
    git -C "$ROOT" worktree remove "$dir"  # refuses if the worktree has uncommitted changes
    echo "- $lane: removed $dir (branch lane/$lane kept)"
  done
}

case "${1:-}" in
  up) shift; cmd_up "$@" ;;
  status) cmd_status ;;
  merge) cmd_merge ;;
  down) shift; cmd_down "$@" ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
