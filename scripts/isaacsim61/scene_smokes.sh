#!/usr/bin/env bash
# Run a suite's scene smokes (robobench/suites/<suite>/smokes/*_smoke.py) one after another on one GPU.
#   scripts/isaacsim61/scene_smokes.sh puzzle                      # all puzzle scene smokes, GPU $GPU (default 0)
#   GPU=2 scripts/isaacsim61/scene_smokes.sh assembly allen_bolt   # only smokes whose name contains a filter word
#   BASE_REPO=/path/to/stock/EmbodiedSWE scripts/isaacsim61/scene_smokes.sh assembly
#       # same smokes on a stock Isaac Sim 5.1 checkout, cameras off (smoke_nocam.py); BASE_PY defaults
#       # to $BASE_REPO/.venv/bin/python
# Logs: $ESW61_OUT/scene/<suite>.<smoke>.log (5.1: <...>_51.log); summary: $ESW61_OUT/scene/<suite>[_51].tsv
# (rc + verdict lines). Smokes that take --out record viewport frames; 6.1 runs turn them into
# $ESW61_OUT/videos/<smoke>.mp4. ESW61_OUT defaults to <repo>/logs/isaacsim61.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUITE="${1:?suite}"; shift
GPU="${GPU:-0}"; TO="${TO:-1800}"; BASE_REPO="${BASE_REPO:-}"
BASE_PY="${BASE_PY:-${BASE_REPO:+$BASE_REPO/.venv/bin/python}}"
export PYTHONUNBUFFERED=1  # some smokes print their verdict without flush right before a hard app exit
ROOT_OUT="${ESW61_OUT:-$REPO/logs/isaacsim61}"
OUT="$ROOT_OUT/scene"; VIDEOS="$ROOT_OUT/videos"; mkdir -p "$OUT" "$VIDEOS"
SRC="$REPO/robobench/suites/$SUITE/smokes"
SUFFIX=""; [[ -n "$BASE_REPO" ]] && SUFFIX="_51"
SUMMARY="$OUT/${SUITE}${SUFFIX}.tsv"; touch "$SUMMARY"

for f in "$SRC"/*_smoke.py; do
  name="$(basename "$f" .py)"
  if [[ $# -gt 0 ]]; then
    hit=0; for w in "$@"; do [[ "$name" == *"$w"* ]] && hit=1; done
    [[ $hit == 0 ]] && continue
  fi
  module="robobench.suites.$SUITE.smokes.$name"
  log="$OUT/$SUITE.$name$SUFFIX.log"
  npz="$(mktemp -u "${TMPDIR:-/tmp}/esw61_${name}${SUFFIX}_XXXX.npz")"
  extra=()
  grep -q '"--out"' "$f" && extra+=(--out "$npz")
  echo "[scene] $module on GPU $GPU${SUFFIX:+ (5.1)}"
  if [[ -n "$BASE_REPO" ]]; then
    (cd "$BASE_REPO" && env -u PYTHONPATH CUDA_VISIBLE_DEVICES="$GPU" OMNI_KIT_ACCEPT_EULA=YES \
      timeout "$TO" "$BASE_PY" "$REPO/scripts/isaacsim61/smoke_nocam.py" "$module" --headless "${extra[@]}") > "$log" 2>&1
  else
    (source "$REPO/compat/isaacsim61/env.sh" && cd "$REPO" && CUDA_VISIBLE_DEVICES="$GPU" \
      timeout "$TO" python -m "$module" --headless "${extra[@]}") > "$log" 2>&1
  fi
  rc=$?
  verdict="$(grep -E "RESULT|ALL PASS|FAIL|Traceback|Error:|verdict|VERDICT|SUCCESS|success=|^[A-Z][A-Z0-9-]+ \||^FIRMNESS|PASS \|" "$log" | grep -v -i "warn" | tail -3 | tr '\n\t' '  ' | cut -c1-400)"
  sed -i "/^$name\t/d" "$SUMMARY"
  printf "%s\trc=%s\t%s\n" "$name" "$rc" "$verdict" >> "$SUMMARY"
  if [[ -z "$BASE_REPO" && -f "$npz" ]]; then
    (source "$REPO/compat/isaacsim61/env.sh" && python - "$npz" "$VIDEOS/$name.mp4" <<'EOF'
import sys, numpy as np, imageio.v2 as imageio
f = np.load(sys.argv[1])["frames"]
if len(f):
    imageio.mimwrite(sys.argv[2], list(f), fps=15, macro_block_size=1)
print(f"[scene] {sys.argv[2]}: {f.shape} std={f.std():.1f} dframe={np.abs(f[1:].astype(int) - f[:-1]).mean() if len(f) > 1 else 0:.2f}")
EOF
    ) >> "$log" 2>&1
  fi
  rm -f "$npz"
  echo "[scene] done $name rc=$rc"
done
sort -o "$SUMMARY" "$SUMMARY"
echo "[scene] summary -> $SUMMARY"
