#!/usr/bin/env python3
"""Write the byte edits that turn the Steam GameAssembly.dll directly into the final patched file.

install.ps1 applies this list itself, so installing from the originals needs no separate patcher
executable. patch_gameassembly_dynamic_ui.py and patch_gameassembly_v2.py remain the source of the
final bytes; this script only records the difference between the two files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BLOCK = 4096
MERGE_GAP = 16


def diff_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for base in range(0, len(a), BLOCK):
        x, y = a[base : base + BLOCK], b[base : base + BLOCK]
        if x == y:
            continue
        i = 0
        while i < len(x):
            if x[i] != y[i]:
                start = i
                while i < len(x) and x[i] != y[i]:
                    i += 1
                if ranges and base + start - ranges[-1][1] <= MERGE_GAP:
                    ranges[-1] = (ranges[-1][0], base + i)
                else:
                    ranges.append((base + start, base + i))
            else:
                i += 1
    return ranges


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--final", type=Path, required=True)
    p.add_argument("--json", type=Path, required=True)
    a = p.parse_args()
    orig = a.original.read_bytes()
    final = a.final.read_bytes()
    if len(final) < len(orig):
        raise SystemExit("final file is shorter than the original")
    common = final[: len(orig)]
    edits = [
        {"name": f"range_{i}", "offset": s, "expected": orig[s:e].hex().upper(), "replacement": common[s:e].hex().upper()}
        for i, (s, e) in enumerate(diff_ranges(orig, common))
    ]
    rebuilt = bytearray(orig)
    for e in edits:
        new = bytes.fromhex(e["replacement"])
        rebuilt[e["offset"] : e["offset"] + len(new)] = new
    rebuilt.extend(final[len(orig) :])
    if bytes(rebuilt) != final:
        raise SystemExit("edit list does not reproduce the final file")
    doc = {
        "schema_version": 1,
        "input_sha256": hashlib.sha256(orig).hexdigest().upper(),
        "output_sha256": hashlib.sha256(final).hexdigest().upper(),
        "edits": edits,
        "append": final[len(orig) :].hex().upper(),
    }
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("edits", len(edits), "append bytes", len(final) - len(orig), doc["output_sha256"][:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
