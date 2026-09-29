# source compat/isaacsim61/env.sh — run this checkout on Isaac Sim 6.1 / Isaac Lab 3.0 EA.
#
# Needs ISAAC61_VENV: a venv with isaacsim 6.1 and Isaac Lab v3.0.0-EA (docs/isaac_sim_6_1.md).
# PYTHONPATH puts this checkout's robobench / robobench_rl first, and this directory's
# sitecustomize.py installs the runtime shims (robobench/compat61.py) at interpreter start-up.

if [[ -z "${ISAAC61_VENV:-}" || ! -x "${ISAAC61_VENV}/bin/python" ]]; then
  echo "[isaacsim61] set ISAAC61_VENV to the Isaac Sim 6.1 / Isaac Lab 3.0 venv (got '${ISAAC61_VENV:-}')" >&2
  return 1 2>/dev/null || exit 1
fi
ESW="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export ESW ISAAC61_VENV
export PYTHONPATH="$ESW/compat/isaacsim61:$ESW:$ESW/rl${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$ISAAC61_VENV/bin:$PATH"
export OMNI_KIT_ACCEPT_EULA="${OMNI_KIT_ACCEPT_EULA:-YES}"
export HEADLESS="${HEADLESS:-1}"
