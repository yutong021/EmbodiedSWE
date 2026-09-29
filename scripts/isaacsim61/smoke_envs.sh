#!/usr/bin/env bash
# Generic build+step smoke for every registered env matching a prefix, JOBS at a time.
#   scripts/isaacsim61/smoke_envs.sh packing                # all packing.* envs on GPU $GPU (default 0)
#   GPU=2 JOBS=3 STEPS=30 scripts/isaacsim61/smoke_envs.sh packing.pen_holder
# Logs: $ESW61_OUT/smoke/<env>.log; summary: $ESW61_OUT/smoke/<prefix>.tsv (env, PASS/FAIL, last error line).
# ESW61_OUT defaults to <repo>/logs/isaacsim61.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/compat/isaacsim61/env.sh" || exit 1
PREFIX="${1:?suite or env prefix}"
GPU="${GPU:-0}"; JOBS="${JOBS:-2}"; STEPS="${STEPS:-30}"; NUM_ENVS="${NUM_ENVS:-2}"; TO="${TO:-600}"
OUT="${ESW61_OUT:-$REPO/logs/isaacsim61}/smoke"; mkdir -p "$OUT"
SUMMARY="$OUT/${PREFIX}.tsv"; : > "$SUMMARY"

mapfile -t ENVS < <(python -m robobench.scripts.smoke --list 2>/dev/null | python -c "
import ast, sys
for line in sys.stdin:
    if line.startswith('envs'):
        for e in ast.literal_eval(line.split(':', 1)[1].strip()):
            if e == '$PREFIX' or e.startswith('$PREFIX.'):
                print(e)")
echo "[smoke] ${#ENVS[@]} envs matching '$PREFIX' on GPU $GPU, $JOBS at a time"

run_one() {
  local env="$1" log="$OUT/$1.log"
  CUDA_VISIBLE_DEVICES="$GPU" timeout "$TO" python -m robobench.scripts.smoke --env "$env" --headless \
    --num_envs "$NUM_ENVS" --steps "$STEPS" > "$log" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]] && grep -q "^RAN " "$log"; then
    printf "%s\tPASS\t%s\n" "$env" "$(grep '^RAN ' "$log" | tail -1)" >> "$SUMMARY"
  else
    local err
    err="$(grep -E "Error|error:|Exception|SMOKE FAILED|Segmentation" "$log" | grep -v -i "warn" | tail -1 | cut -c1-240)"
    printf "%s\tFAIL(rc=%s)\t%s\n" "$env" "$rc" "${err:-no error line}" >> "$SUMMARY"
  fi
  echo "[smoke] done $env rc=$rc"
}
export -f run_one; export OUT SUMMARY GPU STEPS NUM_ENVS TO
printf "%s\n" "${ENVS[@]}" | xargs -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}
sort -o "$SUMMARY" "$SUMMARY"
echo "[smoke] PASS $(grep -c $'\tPASS' "$SUMMARY") / ${#ENVS[@]}  -> $SUMMARY"
