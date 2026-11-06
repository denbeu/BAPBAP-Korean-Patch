#!/usr/bin/env python3
"""Regenerate payload/v2 from the translation tables and the verified v1 game files.

Developer tool, not needed to install the patch. Requires UnityPy.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import sys
from pathlib import Path

import UnityPy

csv.field_size_limit(10**8)
sys.stdout.reconfigure(encoding="utf-8")

TMP_SCRIPT_NAMES = {"TextMeshProUGUI", "TextMeshPro"}
SKIP_SCRIPTS = {"TMP_FontAsset", "TMP_SpriteAsset"}
PH = re.compile(r"\{\d+\}|<[^>]+>")
ASCII = re.compile(rb"^[\x20-\x7e]+$")
FILES = {"sharedassets0.assets": "shared", "level0": "level0", "resources.assets": "resources"}
VER_LITERAL_SKIP: set[str] = set()


def tsv(path: Path, key: str, val: str) -> dict[str, str]:
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            out[r[key].replace("\\n", "\n")] = r[val].replace("\\n", "\n")
    return out


def check_tags(src: str, ko: str, where: str) -> None:
    if sorted(PH.findall(src)) != sorted(PH.findall(ko)):
        raise SystemExit(f"placeholder/tag mismatch in {where}: {src!r} -> {ko!r}")


def strings_in(raw: bytes, start: int = 32):
    i, n = start, len(raw)
    while i + 4 <= n:
        l = struct.unpack_from("<i", raw, i)[0]
        if 1 <= l <= 600 and i + 4 + l <= n:
            s = raw[i + 4 : i + 4 + l]
            if ASCII.match(s):
                end = (i + 4 + l + 3) & ~3
                if not any(raw[i + 4 + l : end]):
                    yield i, s.decode()
                    i = end
                    continue
        i += 4


def tmp_text(raw: bytes):
    """(offset, text) of TMP_Text.m_text; layout is fixed by the Graphic/TMP_Text headers."""
    p = 12
    p += 4
    p += 12
    l = struct.unpack_from("<i", raw, p)[0]
    p += 4 + ((l + 3) & ~3)
    p += 12 + 16 + 4 + 16 + 4
    if struct.unpack_from("<i", raw, p)[0] != 0:
        return None
    p += 4
    l = struct.unpack_from("<i", raw, p)[0]
    if not 0 < l < 4000 or p + 4 + l > len(raw):
        return None
    return p, raw[p + 4 : p + 4 + l].decode("utf-8", "replace")


def script_classes(game_data: Path) -> dict[int, str]:
    env = UnityPy.load(str(game_data / "globalgamemanagers.assets"))
    sf = next(iter(env.files.values()))
    return {pid: o.read().m_ClassName for pid, o in sf.objects.items() if o.type.name == "MonoScript"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-data", type=Path, required=True, help="bapbap_Data folder holding the verified v1 files")
    ap.add_argument("--literal-tsv", type=Path, required=True)
    ap.add_argument("--tmp-tsv", type=Path, required=True)
    ap.add_argument("--strings-tsv", type=Path, required=True)
    ap.add_argument("--metadata-tsv", type=Path, required=True)
    ap.add_argument("--metadata", type=Path, required=True, help="global-metadata.dat")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    literal = tsv(a.literal_tsv, "source_text", "translation")
    tmp_map = tsv(a.tmp_tsv, "source_text", "translation")
    meta_map = tsv(a.metadata_tsv, "source_text", "translation")
    for s, k in literal.items():
        check_tags(s, k, "literal")
    for s, k in tmp_map.items():
        check_tags(s, k, "tmp")
    for s, k in meta_map.items():
        check_tags(s, k, "metadata")

    # Phrase table -> payload
    with a.strings_tsv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    if len(rows) != 1690:
        raise SystemExit(f"expected 1690 rows, got {len(rows)}")
    for r in rows:
        if r["translation"]:
            check_tags(r["source_text"], r["translation"], r["key"])
    a.out.mkdir(parents=True, exist_ok=True)
    payload = "".join(r["translation"] + "\r\n" for r in rows).encode("utf-8")
    (a.out / "korean-full-v2.txt").write_bytes(payload)

    classes = script_classes(a.game_data)
    stats = {}
    for fname, tag in FILES.items():
        env = UnityPy.load(str(a.game_data / fname))
        sf = next(iter(env.files.values()))
        ggm = next((i + 1 for i, e in enumerate(sf.externals) if "globalgamemanagers.assets" in e.path), None)
        patches = []
        for pid, o in sf.objects.items():
            if o.type.name != "MonoBehaviour":
                continue
            raw = o.get_raw_data()
            fid, sp = struct.unpack_from("<iq", raw, 16)
            cls = classes.get(sp, "?") if fid == ggm else "?"
            if cls in SKIP_SCRIPTS:
                continue
            found = {}
            for off, s in strings_in(raw):
                if s.startswith("#") and s[1:] in literal and literal[s[1:]] != s[1:]:
                    found[off] = (s, "#" + literal[s[1:]], "literal")
            if cls in TMP_SCRIPT_NAMES:
                t = tmp_text(raw)
                if t and t[0] not in found and t[1] in tmp_map:
                    found[t[0]] = (t[1], tmp_map[t[1]], "TMP_Text.m_text")
            # Offsets stay valid because each object's edits run from the end backwards.
            for off in sorted(found, reverse=True):
                src, ko, field = found[off]
                patches.append({"path_id": pid, "object_type": "MonoBehaviour", "field": field, "original": src, "patched": ko, "length_offset": off})
        if tag == "shared":
            # Canonical glossary spelling; v1 shipped a typo for this one display name.
            patches.append({"path_id": 105234, "object_type": "MonoBehaviour", "field": "_characters[Kat].name", "original": "켓", "patched": "캣"})
        doc = {"schema_version": 1, "steam_build_id": "19658140", "serialized_string_patches": patches}
        (a.out / f"strings_{tag}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        stats[tag] = len(patches)
    print("string patches", stats)

    # Metadata literals: only exact, unique sources.
    md = a.metadata.read_bytes()
    lit_off, lit_size, data_off = struct.unpack_from("<iii", md, 8)
    table = {}
    for i in range(lit_size // 8):
        length, idx = struct.unpack_from("<II", md, lit_off + i * 8)
        table.setdefault(md[data_off + idx : data_off + idx + length].decode("utf-8", "replace"), []).append(i)
    lits = []
    for s, k in meta_map.items():
        if s not in table:
            raise SystemExit(f"metadata literal not found: {s!r}")
        for i in table[s]:
            lits.append({"index": i, "original": s, "patched": k})
    (a.out / "metadata_literals.json").write_text(json.dumps({"schema_version": 1, "literals": lits}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print("metadata literals", len(lits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
