"""Run a scene smoke module unchanged but without cameras / video (checks only).

For baselines on a stock Isaac Sim 5.1 checkout whose RTX does not start on the host driver
(scene_smokes.sh does this with BASE_REPO set):

  cd /path/to/stock/EmbodiedSWE && CUDA_VISIBLE_DEVICES=1 OMNI_KIT_ACCEPT_EULA=YES .venv/bin/python \
      /path/to/this/checkout/scripts/isaacsim61/smoke_nocam.py robobench.suites.packing.smokes.tool_packing_smoke --headless
"""

import runpy
import sys

from isaaclab.app import AppLauncher

init = AppLauncher.__init__


def __init__(self, launcher_args=None, **kwargs):
    if launcher_args is not None and not isinstance(launcher_args, dict):
        launcher_args.enable_cameras = False
    else:
        kwargs["enable_cameras"] = False
    init(self, launcher_args, **kwargs)


AppLauncher.__init__ = __init__
sys.modules["omni.replicator.core"] = None  # the smoke's recording block falls back to "no video"

module = sys.argv[1]
sys.argv = [module, *sys.argv[2:]]
runpy.run_module(module, run_name="__main__", alter_sys=True)
