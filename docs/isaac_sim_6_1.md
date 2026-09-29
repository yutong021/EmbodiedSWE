# Isaac Sim 6.1 / Isaac Lab 3.0 EA port

The `isaacsim-6.1` branch ports EmbodiedSWE-Bench from Isaac Sim 5.1 / Isaac Lab 2.3.2 to Isaac Sim 6.1 / Isaac Lab 3.0 EA. It is a version adaptation only: tasks, scenes, rooms, rubrics and configs are unchanged, and a task counts as ported only when its smokes behave as they do on 5.1.

Upstream base: `d34837e` (main). The port is partial; the status table below is the source of truth for what is verified.

## Status

A task is **verified** when its build+step smoke passes and its scene smoke (rubric / oracle / negative cases) gives the same verdict and measurements as the stock 5.1 checkout. **Runs** means the build+step smoke passes but the scene smoke has not been compared yet.

| Suite | Build+step smoke (envs × robots × controllers) | Scene smokes |
|---|---|---|
| packing | 31/31 | 5/5 verified |
| puzzle | 50/50 | 5/6 verified, 1 known issue |
| assembly | 145/145 | 6/11 verified, 4 known issues, 1 unverified |
| cutting | 210/210 | not compared yet (runs) |
| locomanip | 9/9 | not compared yet (runs) |
| deformable | not on this stack | see [Deformable](#deformable) |
| simgen | empty task corpus | nothing to port |

| Task | 6.1 scene smoke | 5.1 scene smoke | Status |
|---|---|---|---|
| packing / clear_organic_objects | ALL PASS 12/12 | same | verified |
| packing / egg_carton | ALL PASS 18/18 | same | verified |
| packing / fruits_on_plate | ALL PASS 13/13 | same | verified |
| packing / pen_holder | ALL PASS 19/19, demo SUCCESS | same | verified |
| packing / tool_packing | FAIL at "score must be 60" (scissors not counted as stowed) | same step, same numbers | verified (the smoke fails upstream too) |
| puzzle / classify_objects | ALL PASS 7/7 | same | verified |
| puzzle / coffee_service | ALL PASS | same | verified |
| puzzle / push_shapes | ALL PASS 32/32 | same | verified |
| puzzle / stack_blocks | ALL PASS 13/13 | same | verified |
| puzzle / syringe_dosing | ALL PASS | same | verified |
| puzzle / spatula_flip_serve | FAIL 22/26 | 26/26 | **known issue** |
| assembly / allen_bolt | seated 1/1 | same | verified |
| assembly / allen_key | seated 1/1 | same | verified |
| assembly / nut_thread | nut 0.6 mm | 1.0 mm | verified |
| assembly / pc_gpu | seated 1/1 | same | verified |
| assembly / pc_ram | 2/2 | same | verified |
| assembly / so101 | M2 4/4, M3 8/8 | same | verified |
| assembly / bulb_assembly | bulb falls through the socket, timeout | seated, 21.8 mm | **known issue** |
| assembly / pc_motherboard | 6/7 bolts | 7/7 | **known issue** |
| assembly / pc_motherboard_gpu_ram | 9/10 parts | 10/10 | **known issue** |
| assembly / ikea_table_assembly | seated 0/4, leg slip 23–30 mm | seated 0/4, leg slip 2–6 mm | **known issue** |
| assembly / ikea_table_assembly_reachable | rc=0, no verdict line | no baseline (5.1 venv lacks pinocchio) | unverified |
| cutting / dice, slice | not run | | runs |
| locomanip / box_to_bin, fruit_delivery, wheel_carry | not run | | runs |

When a task changes status, update its row in the same commit as the fix.

## Setup

Tested stack:

| Component | Version |
|---|---|
| Isaac Sim | 6.1.0.0 (pip) |
| Isaac Lab | `v3.0.0-EA` (`ae37b028`), all `source/*` packages installed editable into the same venv |
| Python / torch / warp | 3.12 / 2.11.0+cu128 / 1.17.0 |
| Extra packages | `pin 4.1.0`, `pin-pink 3.3.0`, `daqp 0.8.5` (pink_ik), `imageio-ffmpeg 0.6.0`, `moviepy 2.2.1` (push_shapes video) |
| NVIDIA driver | 610.57.04 |

Point `ISAAC61_VENV` at that venv and source the env script from the checkout (or from the submodule path in a parent repo):

```bash
export ISAAC61_VENV=/path/to/isaacsim61/.venv
source compat/isaacsim61/env.sh
python -c "import robobench, robobench_rl; print(robobench.__file__, robobench_rl.__file__)"   # both inside this checkout
```

`env.sh` puts `$ISAAC61_VENV/bin` first on `PATH`, sets `PYTHONPATH=compat/isaacsim61:<repo>:<repo>/rl` (so this checkout wins over any editable install in the venv), and sets `OMNI_KIT_ACCEPT_EULA=YES` and `HEADLESS=1` unless already set. `compat/isaacsim61/sitecustomize.py` installs the runtime shims at interpreter start-up and then chains any existing `sitecustomize`. `COMPAT61_DISABLE=1` turns the shims off for debugging.

## Runtime shims (`robobench/compat61.py`)

Most Isaac Lab 3.0 API changes are absorbed here so task code changes stay small.

| 3.0 change | Shim |
|---|---|
| `--headless` CLI flag removed (kwarg and `HEADLESS` env remain) | `add_app_launcher_args` adds `--headless` back |
| RTX (Vulkan) ignores `CUDA_VISIBLE_DEVICES`, numbers GPUs physically and spreads over every visible GPU | with cameras on (`enable_cameras=True` or `ENABLE_CAMERAS=1`), pins RTX to the sim's physical GPU (`--/renderer/activeGpu`, multi-GPU off); extra kit args via `COMPAT61_KIT` |
| `.data.*` returns `ProxyArray`; TorchScript math functions reject it | after app start, every public function in `isaaclab.utils.math` unwraps `ProxyArray` arguments |
| `SimulationContext.set_render_mode` / `RenderMode` removed; `set_camera_view` lost `camera_prim_path`; headless `render()` no longer pumps Kit, so viewport annotators get no frames | `patch_sim()`: no-op `set_render_mode`, `set_camera_view(..., camera_prim_path=)` writes the camera pose on the session layer, and every `render()` after first use pumps an RTX update |
| `root_physx_view` deprecated; `root_view` reads/writes warp arrays | explicit helper `physx_view(asset)`: `get_*` returns torch copies, `set_*(data, indices)` takes torch |

Limits observed on this build (not fixable in the shims): `num_envs >= 434` drops ground contact for some bodies, and with the `factory001` room plus cameras RTX's 2^14-lights-per-stage cap limits runs to 364 envs (`compat61.MAX_ENVS`, `MAX_ENVS_ROOM_CAMERAS`).

## Migration rules

Apply these when porting a task that is not ported yet, or new upstream code.

1. **Quaternions are xyzw everywhere**: `InitialStateCfg.rot`, `root_state[:, 3:7]`, `body_*_w[..., 3:7]`, inputs and outputs of `isaaclab.utils.math`, spawner `orientation`, and absolute-pose actions `[pos3, quat4]` (pink_ik, franka). USD `Gf.Quatf` / `Gf.Quatd` stay real-first; leave them alone. In code that does its own quaternion math, convert only at the boundaries.
   - yaw about z: wxyz `(c, 0, 0, s)` is xyzw `(0, 0, s, c)`; `X[:, 3] = cos; X[:, 6] = sin` becomes `X[:, 5] = sin; X[:, 6] = cos`
   - identity: `X[:, 3] = 1` becomes `X[:, 6] = 1`; conjugate negates `[..., :3]`
   - trap: wxyz `(0, 0, 0, 1)` is a 180° yaw, i.e. xyzw `(0, 0, 1, 0)`, not the identity
   - component-wise code (`w, x, y, z = q`, `atan2`, `q[..., 0]`) must be ported by hand
   - `python scripts/isaacsim61/quat_codemod.py FILE...` prints a diff of the mechanical rewrites (`--write` applies) and flags lines that need a human; always review the diff
2. **`ProxyArray`**: `.device`, `.dtype` and `.shape` are warp's. Use `.torch` wherever a torch tensor is needed (arithmetic that mixes devices/dtypes, `torch.*` calls, storing state).
3. **PhysX view**: `X.root_physx_view.get_masses()` becomes `physx_view(X).get_masses()` (`from robobench.compat61 import physx_view`).
4. **Jacobian / mass matrix**: `art.data.body_link_jacobian_w.torch[...]`, `art.data.mass_matrix.torch`; indexing is unchanged.
5. **Actuators**: `effort_limit_sim` / `velocity_limit_sim` become `joint_effort_limit` / `joint_velocity_limit`; mixing the two sets raises a conflict.
6. **Sim config**: `SimulationCfg(physics=PhysxCfg(...))` with `PhysxCfg` from `isaaclab_physx.physics`; `RenderCfg` is gone and render fields go through `robobench.core.config.apply_render_settings` (`IsaacRtxRendererGlobalSettingsCfg`).
7. **Regex prim paths**: `{ENV_REGEX_NS}` resolves to `env_[^/]+`; hand-written patterns must match that.
8. **pink_ik**: 3.0 takes task configs (`LocalFrameTaskCfg`, `NullSpacePostureTaskCfg`) and builds the tasks itself; `LocalFrameTask` imports from `isaaclab.controllers.pink_ik.pink_tasks`. `import pinocchio` still has to happen before `AppLauncher`.

## Verification

```bash
# (a) build + step every registered env (robot × controller) matching a prefix
GPU=1 JOBS=4 STEPS=30 NUM_ENVS=2 scripts/isaacsim61/smoke_envs.sh puzzle
#     -> $ESW61_OUT/smoke/<env>.log, $ESW61_OUT/smoke/puzzle.tsv  (ESW61_OUT defaults to logs/isaacsim61)

# (b) scene smokes (task semantics + viewport video), optionally filtered by name
GPU=1 scripts/isaacsim61/scene_smokes.sh assembly allen_bolt
#     -> $ESW61_OUT/scene/assembly.<smoke>.log, assembly.tsv, videos/<smoke>.mp4

# (c) the same scene smokes on a stock 5.1 checkout for comparison (cameras off, checks unchanged)
BASE_REPO=/path/to/stock/EmbodiedSWE GPU=1 scripts/isaacsim61/scene_smokes.sh assembly allen_bolt
#     -> assembly.<smoke>_51.log, assembly_51.tsv

# (d) RL path
python rl/scripts/smoke.py --task pen_holder_franka_osc_tuned --reward dense --num_envs 2 --steps 5 --device cuda:0
```

When a 6.1 scene smoke fails, run it on 5.1 before calling it a port bug: several smokes fail or are marginal upstream. The 5.1 comparison uses `scripts/isaacsim61/smoke_nocam.py`, which runs the smoke module unchanged with cameras and recording off, because 5.1's RTX does not start on driver 610.

Practical notes:

- Do not run several scene smokes on one GPU at once: PhysX asks for 512 MB up front and fails with `Failed to create simulation view` when memory is tight.
- Check that recorded video is real: frame std ≈ 0 or mean frame-to-frame difference ≈ 0 means the camera is misaimed or RTX is not being pumped (`scene_smokes.sh` prints both).
- 5.1 pitfalls: with cameras on, `CUDA_VISIBLE_DEVICES` crashes RTX (select with `--device cuda:N`); `SimulationApp.close()` can hang, so custom scripts end with `os._exit(0)` and print with `flush=True`.

## Known issues and leads

All four failing assembly tasks and spatula_flip_serve involve sustained contact or externally applied wrenches. Two runtime differences from 5.1 have been identified; neither is applied on this branch, because each changes behaviour for every task and needs a full re-verification first.

- **`PhysxCfg.enable_external_forces_every_iteration`** defaults to `True` in Isaac Lab 3.0 and was `False` in 2.3.2 (the only `PhysxCfg` default that differs). Forcing `False` for all scenes brings pc_motherboard_gpu_ram to 10/10, cuts ikea_table leg slip to 0.5–1.3 mm and lifts spatula_flip_serve to 24/26 (still failing).
- **bulb_assembly**: on 6.1 PhysX nothing collides with the socket nut's SDF collider (not even a convex hull), so the bulb drops through. Authoring `physxSDFMeshCollision:sdfBitsPerSubgridPixel = BitsPerPixel32` on `/BulbSocket/nut` only (not on the thread) makes the nut–thread pair resolve on the thread's SDF and the bulb seats at 21.5 mm. The value must be composed into the asset (for example through a wrapper layer that references it); writing it on the live stage after the prim exists, even before `sim.reset()`, is ignored.
- pc_motherboard (6/7 bolts) has not been re-run with the external-forces change.

## Deformable

The deformable suite targets a different stack (Isaac Sim 6.0 + Isaac Lab develop + Newton) and runs unchanged in the `env_newton` environment described in `robobench/suites/deformable/README.md`; this branch does not touch it. Results in that environment on upstream code: tshirt_fold, knot and latte_pour pass; aloha_lift fails (lace ends lifted to 94/139 mm, but one lace tears: max joint gap 15.7 mm vs 5.8 mm at rest). The dumpling and generic deformable envs have not been run there.

## Maintaining the branch

- Parent repos pin this branch as a submodule, so published history is never rewritten: bring in upstream with `git merge upstream/main`, not rebase.
- Port new or changed upstream tasks with the migration rules, run (a) and (b), compare with 5.1 via (c), and record the result in the status table.
- `robobench/compat61.py` and `compat/isaacsim61/` are the only shared runtime additions; task-level fixes stay in the task's own files.
