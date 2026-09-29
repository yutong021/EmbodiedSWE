"""Auto-loaded (PYTHONPATH from env.sh): install the Isaac Sim 6.1 shims, then chain the system sitecustomize."""

import importlib.util
import os
import sys

try:
    from robobench.compat61 import install

    install()
except Exception as e:  # noqa: BLE001 — never break interpreter startup
    print(f"[isaacsim61 sitecustomize] compat61 not installed: {e}", file=sys.stderr)

_here = os.path.dirname(os.path.abspath(__file__))
for _p in sys.path:
    _f = os.path.join(_p or ".", "sitecustomize.py")
    if os.path.abspath(os.path.dirname(_f)) != _here and os.path.isfile(_f):
        _spec = importlib.util.spec_from_file_location("_system_sitecustomize", _f)
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))
        break
