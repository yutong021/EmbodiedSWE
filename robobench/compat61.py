"""Isaac Sim 6.1 / Isaac Lab 3.0 EA runtime shims (docs/isaac_sim_6_1.md).

`install()` hooks `AppLauncher.__init__` (loaded by compat/isaacsim61/sitecustomize.py, which
compat/isaacsim61/env.sh puts on PYTHONPATH):

* `--headless` is re-added to `add_app_launcher_args` (3.0 removed the flag, not the setting);
* camera runs pin RTX to the sim's GPU (`activeGpu`, `multiGpu` off); otherwise RTX spreads over
  every visible GPU, including ones other jobs use;
* after the app is up, every public function in `isaaclab.utils.math` unwraps `ProxyArray`
  arguments — the TorchScript ones cannot take `.data.*` values directly;
* `SimulationContext` regains the viewport-recording API the smokes use (`patch_sim`).

Explicit helper (imported by call sites): `physx_view(asset)`, a torch-I/O stand-in for the old
`asset.root_physx_view`.

Limits observed on this build (driver 610.57.04; not fixable here): >= 434 envs drop ground contact
for some bodies (keep <= 433); RTX caps a stage at 2**14 lights (factory001 room: 45 lights per
env -> <= 364 envs).
"""

from __future__ import annotations

import os
import sys
from typing import Any

MAX_ENVS = 433
MAX_ENVS_ROOM_CAMERAS = 364


def as_tensor(value: Any) -> Any:
    """ProxyArray -> torch.Tensor; anything else unchanged."""
    return getattr(value, "torch", value) if type(value).__name__ == "ProxyArray" else value


class _TorchPhysxView:
    """PhysX tensor view with the Isaac Lab 2.x torch-frontend I/O: `get_*` returns a torch copy,
    `set_*(data, indices)` takes torch. Everything else passes through to the warp-frontend view."""

    def __init__(self, view):
        object.__setattr__(self, "_view", view)

    def __getattr__(self, name):
        attr = getattr(self._view, name)
        if not callable(attr) or not (name.startswith("get_") or name.startswith("set_")):
            return attr
        import torch
        import warp as wp

        def to_wp(x, index=False):
            if not torch.is_tensor(x):
                return x
            x = x.contiguous()
            if index:
                return wp.from_torch(x.to(torch.int32), dtype=wp.int32)
            return wp.from_torch(x.float() if x.is_floating_point() else x)

        if name.startswith("get_"):
            def get(*a, **k):
                out = attr(*a, **k)
                return wp.to_torch(out).clone() if isinstance(out, wp.array) else out
            return get

        def set_(data, indices=None, *a, **k):
            if indices is None:
                return attr(to_wp(data), *a, **k)
            return attr(to_wp(data), to_wp(indices, index=True), *a, **k)
        return set_


def physx_view(asset) -> Any:
    """`asset.root_physx_view` with torch in/out (Isaac Lab 3.0 views speak warp)."""
    return _TorchPhysxView(asset.root_view)


def rtx_kit_args(device: str) -> str:
    """RTX (Vulkan) ignores CUDA_VISIBLE_DEVICES and numbers GPUs physically: map the sim's CUDA
    device back to its physical index so rendering and simulation share one GPU."""
    args = "--/rtx/verifyDriverVersion/enabled=false --/renderer/multiGpu/enabled=false"
    idx = int(device.split(":")[1]) if device.startswith("cuda:") else 0
    visible = [v.strip() for v in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if v.strip()]
    if visible:
        if idx >= len(visible) or not visible[idx].isdigit():
            return args
        idx = int(visible[idx])
    return f"{args} --/renderer/activeGpu={idx}"


def patch_math() -> None:
    import functools
    import inspect

    import isaaclab.utils.math as m

    if getattr(m, "_compat61", False):
        return

    def wrap(f):
        @functools.wraps(f)
        def g(*a, **k):
            return f(*[as_tensor(x) for x in a], **{kk: as_tensor(v) for kk, v in k.items()})
        return g

    for name, fn in list(vars(m).items()):
        if name.startswith("_") or not callable(fn) or inspect.isclass(fn):
            continue
        if getattr(fn, "__module__", None) != m.__name__ and not hasattr(fn, "graph"):
            continue
        setattr(m, name, wrap(fn))
    m._compat61 = True


def patch_sim() -> None:
    """Viewport-recording API the smokes use, gone from 3.0's `SimulationContext`:
    `set_render_mode` / `RenderMode` (no-op now), `set_camera_view(..., camera_prim_path=)` (3.0
    only moves visualizers), and a Kit app pump per `render()` so viewport annotators get frames
    headless (3.0 pumps only for camera sensors / visualizers). The pump starts on first use."""
    import enum

    from isaaclab.sim import SimulationContext as S

    if getattr(S, "_compat61", False):
        return

    class RenderMode(enum.IntEnum):
        NO_GUI_OR_RENDERING = -1
        NO_RENDERING = 0
        PARTIAL_RENDERING = 1
        FULL_RENDERING = 2

    def _pump(self) -> None:
        if getattr(self, "_compat61_pump", False):
            return
        from isaaclab_physx.renderers.isaac_rtx_renderer_utils import ensure_isaac_rtx_render_update

        self.add_render_callback("compat61_viewport_pump", lambda _: ensure_isaac_rtx_render_update(force=True), order=100)
        self._compat61_pump = True

    def set_render_mode(self, mode) -> None:
        _pump(self)

    orig_view = S.set_camera_view

    def set_camera_view(self, eye, target, camera_prim_path: str | None = None) -> None:
        orig_view(self, eye, target)
        if camera_prim_path is None:
            return
        import omni.usd
        from pxr import Gf, Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(camera_prim_path)
        if not prim:
            return
        view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*map(float, eye)), Gf.Vec3d(*map(float, target)), Gf.Vec3d(0, 0, 1))
        # Kit's viewport cameras (/OmniverseKit_*) keep their xform ops on the session layer.
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            xf = UsdGeom.Xformable(prim)
            xf.ClearXformOpOrder()
            xf.AddTransformOp(opSuffix="compat61").Set(view.GetInverse())
        _pump(self)

    S.RenderMode = RenderMode
    S.set_render_mode = set_render_mode
    S.set_camera_view = set_camera_view
    S._compat61 = True


def _patch_launcher(cls) -> None:
    if getattr(cls, "_compat61", False):
        return
    init = cls.__init__

    def __init__(self, launcher_args=None, **kwargs):
        get = (lambda k, d=None: getattr(launcher_args, k, d)) if launcher_args is not None and not isinstance(launcher_args, dict) \
            else (lambda k, d=None: {**(launcher_args or {}), **kwargs}.get(k, d))
        if get("enable_cameras", False) or os.environ.get("ENABLE_CAMERAS") == "1":
            extra = rtx_kit_args(str(get("device", "cuda:0") or "cuda:0"))
            kit = f"{get('kit_args', '') or ''} {extra} {os.environ.get('COMPAT61_KIT', '')}".strip()
            if launcher_args is None or isinstance(launcher_args, dict):
                kwargs["kit_args"] = kit
            else:
                launcher_args.kit_args = kit
        init(self, launcher_args, **kwargs)
        patch_math()
        patch_sim()

    add_args = cls.add_app_launcher_args

    def add_app_launcher_args(parser):
        add_args(parser)
        # Isaac Lab 3.0 dropped the CLI flag (the kwarg / HEADLESS env remain); scripts still pass it
        if "--headless" not in parser._option_string_actions:
            parser.add_argument("--headless", action="store_true", default=os.environ.get("HEADLESS") == "1")

    cls.__init__ = __init__
    cls.add_app_launcher_args = staticmethod(add_app_launcher_args)
    cls._compat61 = True


class _Hook:
    """Patch AppLauncher the moment `isaaclab.app.app_launcher` finishes executing."""

    TARGET = "isaaclab.app.app_launcher"

    def find_spec(self, name, path=None, target=None):
        if name != self.TARGET:
            return None
        sys.meta_path.remove(self)
        try:
            from importlib.util import find_spec
            spec = find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return spec
        exec_module = spec.loader.exec_module

        def run(module):
            exec_module(module)
            _patch_launcher(module.AppLauncher)

        spec.loader.exec_module = run
        return spec


def install() -> None:
    if os.environ.get("COMPAT61_DISABLE") == "1" or any(isinstance(h, _Hook) for h in sys.meta_path):
        return
    mod = sys.modules.get(_Hook.TARGET)
    if mod is not None:
        _patch_launcher(mod.AppLauncher)
    else:
        sys.meta_path.insert(0, _Hook())
