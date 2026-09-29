"""wxyz -> xyzw codemod for the Isaac Lab 3.0 port (mechanical patterns only; review the diff).

  python scripts/isaacsim61/quat_codemod.py FILE...            # dry run: print a unified diff
  python scripts/isaacsim61/quat_codemod.py --write FILE...    # apply

Rewrites
  1. yaw pair on a (.., 13)/(.., 7) state:  X[:, 3] = cos(h) ; X[:, 6] = sin(h)
       -> X[:, 5] = sin(h) ; X[:, 6] = cos(h)
  2. identity on a state:  X[:, 3] = 1.0  -> X[:, 6] = 1.0
  3. 4-tuple literals bound to a quaternion-named key/kwarg/field
       (rot / *_rot / orient / orientation / *_quat / quat)  (w, x, y, z) -> (x, y, z, w)
Flags (not rewritten) lines that need a human: component comments (# w), atan2 on quats,
torch.tensor quaternion literals, `[..., 0]` reads of quats.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

NUM = r"[-+]?\s*(?:[\w.]+(?:\([^()]*\))?(?:\s*[*/]\s*[\w.]+(?:\([^()]*\))?)*)"
TUP = re.compile(rf"\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*,?\s*\)")
KEY = re.compile(r"""(?P<key>(?:\b(?:base_)?rot|\b\w+_rot|\borient(?:ation)?|\b\w*_quat|\bquat)\b\s*(?:[:=]|["']\s*:)\s*(?:tuple\[[^\]]*\]\s*=\s*)?)$""")
KEYQ = re.compile(r"""(?P<key>["'](?:rot|orient|orientation|quat|\w+_rot|\w+_quat)["']\s*:\s*)$""")

YAW = re.compile(r"^(?P<ind>\s*)(?P<x>[\w.\[\]]+)\[(?P<pre>:|\.\.\.), ?3\] = (?P<cos>.*\bcos\b.*)$")
ID3 = re.compile(r"^(?P<ind>\s*)(?P<x>\w+)\[(?P<pre>:|\.\.\.), ?3\] = 1(?:\.0)?(?P<rest>\s*(?:#.*)?)$")
FLAG = [
    (re.compile(r"#\s*[wxyz]\b"), "component comment"),
    (re.compile(r"atan2\(.*quat|atan2\(.*\bq\w*\["), "atan2 on quaternion"),
    (re.compile(r"torch\.tensor\(\s*\[\s*1\.0?\s*,\s*0\.0?\s*,\s*0\.0?\s*,\s*0\.0?\s*\]"), "tensor identity literal"),
    (re.compile(r"quat\w*\[(?::|\.\.\.), ?0\]|\bq\w*\[(?::|\.\.\.), ?0\]"), "reads quat[...,0]"),
    (re.compile(r"Gf\.Quat[fd]"), "USD Gf.Quat (real-first; leave)"),
]


def rewrite_tuples(line: str) -> str:
    out, pos = [], 0
    for m in TUP.finditer(line):
        before = line[:m.start()]
        if KEY.search(before) or KEYQ.search(before):
            w, x, y, z = (g.strip() for g in m.groups())
            out.append(line[pos:m.start()] + f"({x}, {y}, {z}, {w})")
            pos = m.end()
    out.append(line[pos:])
    return "".join(out)


def transform(src: str) -> tuple[str, list[str]]:
    lines = src.split("\n")
    flags = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = YAW.match(ln)
        if m and i + 1 < len(lines):
            m2 = re.match(rf"^(\s*){re.escape(m['x'])}\[{re.escape(m['pre'])}, ?6\] = (.*\bsin\b.*)$", lines[i + 1])
            if m2:
                lines[i] = f"{m['ind']}{m['x']}[{m['pre']}, 5] = {m2.group(2)}"
                lines[i + 1] = f"{m2.group(1)}{m['x']}[{m['pre']}, 6] = {m['cos']}"
                i += 2
                continue
        m = ID3.match(ln)
        if m:
            lines[i] = f"{m['ind']}{m['x']}[{m['pre']}, 6] = 1.0{m['rest']}"
        else:
            lines[i] = rewrite_tuples(ln)
        for rx, why in FLAG:
            if rx.search(lines[i]):
                flags.append(f"{i + 1}: [{why}] {lines[i].strip()[:140]}")
        i += 1
    return "\n".join(lines), flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    for f in a.files:
        p = Path(f)
        src = p.read_text()
        dst, flags = transform(src)
        if dst != src:
            sys.stdout.writelines(difflib.unified_diff(src.splitlines(True), dst.splitlines(True), str(p), str(p), n=0))
            if a.write:
                p.write_text(dst)
        for fl in flags:
            print(f"FLAG {p}:{fl}")


if __name__ == "__main__":
    main()
