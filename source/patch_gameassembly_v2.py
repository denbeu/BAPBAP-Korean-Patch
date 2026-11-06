#!/usr/bin/env python3
"""Second GameAssembly.dll patch layer, applied on top of the verified v1 output.

Fixes:
  * Friend list nickname loses its last character.
      UILobbyFriendEntry.Initialise calls TMP_FontAsset.HasCharacters, which only checks
      the primary font (never the fallbacks), then loops over the "missing" characters
      doing `result = name.Replace(c, "")` on the *original* name, so only the last
      missing character is removed. Any Hangul nickname therefore loses its last syllable
      even though the fallback font could render it. The patch skips that removal.
  * Korean word order of stat fragments (`-150 <icon>Health` -> `<icon>Health -150`).
      ItemManager.BuildStatString's final String.Concat(string[9]) is redirected to a helper
      that reorders the array for the Korean slot only. Fragments built by BuildItemStatStr
      for Dmg/DmgPercent keep the number before the name because sentences read
      "<icon>250 피해를 줍니다", with the icon moved in front of the number.
  * Ability damage fragments get the same `<icon>250 피해` order for the Korean slot only.
  * Berserk/Vengeance cap fragment `{0}% {1}` becomes `{1} {0}%` for the Korean slot only.
  * The lobby-socket "disconnected" notice stays hidden during a match. The match itself runs
    on a separate WebRTC connection, so the notice only distracts there. Every locale.

The script writes a JSON edit list. install.ps1 applies that list with per-range byte guards,
so end users need no Python. The edit list is only valid for the exact v1 output hash.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import pefile

_v1_path = Path(__file__).with_name("patch_gameassembly_dynamic_ui.py")
_spec = importlib.util.spec_from_file_location("patch_gameassembly_dynamic_ui", _v1_path)
v1 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v1
_spec.loader.exec_module(v1)

V1_SHA256 = "BB7F8A6A46FF8C1BEB4B9D97F4EB0F6952ECB283592DCD929EB11CDFCD6DA413"
MARKER_V2 = b"BAPKO_V2\0"

STRING_CONCAT_ARRAY_VA = 0x1821E1A00
STRING_FORMAT_2ARGS_VA = v1.STRING_FORMAT_2ARGS_VA
IL2CPP_STRING_NEW_VA = v1.IL2CPP_STRING_NEW_VA

STATS_DMG = 1
STATS_DMG_PERCENT = 17

# VA, original bytes
FRIEND_NAME_BRANCH = (0x1805884A9, bytes.fromhex("0F8505010000"))
ITEM_STAT_MARKER = (0x180B433C7, bytes.fromhex("48C744242800000000"))
STAT_PASS_STAT_ID = (0x180B437CA, bytes.fromhex("33D2"))
STAT_CONCAT_JMP_VA = 0x180B437ED
CAP_FORMAT_CALLS = (0x180934125, 0x1809347DE)
# String.Format(string, object[]) calls that consume "<color=#{0}><b>{1}</b>{2}</color> {3}".
# SpriestExpungeAbility also loads that literal, but v1 already redirects its call.
STRING_FORMAT_ARRAY_VA = v1.STRING_FORMAT_ARRAY_VA
DAMAGE_FORMAT_CALLS = (0x1806F6CF9, 0x1806F6A2E, 0x18076AE6A, 0x180742A6B, 0x180708A93, 0x1808E04B5)
# Lobby socket "disconnected" notice. UIManager.lobbyRoot is inactive between
# GameManager.ClOnMatchStarted and ClMatchmakingEnd, so it identifies "in a match".
DISCONNECT_NOTICE_JMP_VA = 0x18063A9AF  # LoginController socket-disconnected callback
SHOW_DISCONNECTED_VA = 0x18061CFE0
HIDE_DISCONNECTED_VA = 0x18061B860
MATCH_START_CLOSE_LOBBY_CALL_VA = 0x180673D0B  # GameManager.ClOnMatchStarted
CLOSE_LOBBY_UI_VA = 0x18067F0D0
GAMEOBJECT_ACTIVE_SELF_VA = 0x18328ABC0
UI_MANAGER_LOBBY_OFFSET = 0x2E0
UI_MANAGER_LOBBY_ROOT_OFFSET = 0x2E8
UI_LOBBY_SPLASH_OFFSET = 0x30


def build_stat_helper(va: int, gt: int, open_b: int, close: int, b_only: int) -> bytes:
    """rcx=string[9]; edx=stat id; entry [rsp+30h] low byte=1 when called from BuildItemStatStr.

    Array on entry: "<color=#", hex, "><b>", value, "</b> ", sprite, " ", name, "</color>".
    Korean slot results:
      damage inside a sentence: <color=#hex>sprite<b>value</b> name</color>
      everything else:          <color=#hex>sprite name <b>value</b></color>
    """
    b = v1.X64Builder(va)
    b.emit(b"\x48\x83\xEC\x28")  # sub rsp,28h
    b.emit(b"\x48\x89\x4C\x24\x20")  # mov [rsp+20h],rcx
    v1.emit_language_37_check(b, "orig")
    b.emit(b"\x80\x7C\x24\x58\x01")  # cmp byte ptr [rsp+58h],1
    b.jne("reorder")
    b.emit(b"\x83\xFA" + bytes((STATS_DMG,)))  # cmp edx,1
    b.je("icon_first")
    b.emit(b"\x83\xFA" + bytes((STATS_DMG_PERCENT,)))  # cmp edx,17
    b.je("icon_first")
    b.mark("reorder")
    b.lea_rcx_rip(gt)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x89\x44\x24\x30")  # mov [rsp+30h],rax
    b.lea_rcx_rip(open_b)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x89\x44\x24\x38")  # mov [rsp+38h],rax
    b.lea_rcx_rip(close)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x4C\x8B\x54\x24\x20")  # mov r10,[rsp+20h]
    b.emit(b"\x49\x8B\x52\x38")  # mov rdx,[r10+38h]  value
    b.emit(b"\x4D\x8B\x42\x48")  # mov r8,[r10+48h]   sprite
    b.emit(b"\x4D\x8B\x4A\x50")  # mov r9,[r10+50h]   " "
    b.emit(b"\x4D\x8B\x5A\x58")  # mov r11,[r10+58h]  name
    b.emit(b"\x49\x89\x42\x60")  # mov [r10+60h],rax  "</b></color>"
    b.emit(b"\x48\x8B\x44\x24\x30")  # mov rax,[rsp+30h]
    b.emit(b"\x49\x89\x42\x30")  # mov [r10+30h],rax  ">"
    b.emit(b"\x4D\x89\x42\x38")  # mov [r10+38h],r8   sprite
    b.emit(b"\x4D\x89\x4A\x40")  # mov [r10+40h],r9   " "
    b.emit(b"\x4D\x89\x5A\x48")  # mov [r10+48h],r11  name
    b.emit(b"\x48\x8B\x44\x24\x38")  # mov rax,[rsp+38h]
    b.emit(b"\x49\x89\x42\x50")  # mov [r10+50h],rax  " <b>"
    b.emit(b"\x49\x89\x52\x58")  # mov [r10+58h],rdx  value
    b.jmp("orig")
    b.mark("icon_first")
    b.lea_rcx_rip(gt)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x89\x44\x24\x30")  # mov [rsp+30h],rax
    b.lea_rcx_rip(b_only)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x4C\x8B\x54\x24\x20")  # mov r10,[rsp+20h]
    b.emit(b"\x49\x8B\x52\x38")  # mov rdx,[r10+38h]  value
    b.emit(b"\x4D\x8B\x42\x40")  # mov r8,[r10+40h]   "</b> "
    b.emit(b"\x4D\x8B\x4A\x48")  # mov r9,[r10+48h]   sprite
    b.emit(b"\x49\x89\x42\x40")  # mov [r10+40h],rax  "<b>"
    b.emit(b"\x48\x8B\x44\x24\x30")  # mov rax,[rsp+30h]
    b.emit(b"\x49\x89\x42\x30")  # mov [r10+30h],rax  ">"
    b.emit(b"\x4D\x89\x4A\x38")  # mov [r10+38h],r9   sprite
    b.emit(b"\x49\x89\x52\x48")  # mov [r10+48h],rdx  value
    b.emit(b"\x4D\x89\x42\x50")  # mov [r10+50h],r8   "</b> "
    b.mark("orig")
    b.emit(b"\x48\x8B\x4C\x24\x20")  # mov rcx,[rsp+20h]
    b.emit(b"\x33\xD2")  # xor edx,edx
    b.emit(b"\x48\x83\xC4\x28")  # add rsp,28h
    b.jmp_abs(STRING_CONCAT_ARRAY_VA)
    return b.finish()


def build_damage_format_helper(va: int, fmt: int) -> bytes:
    """String.Format(rcx=fmt, rdx=object[]) for the ability damage fragment, Korean slot only."""
    b = v1.X64Builder(va)
    b.emit(b"\x48\x83\xEC\x28")  # sub rsp,28h
    b.emit(b"\x48\x89\x4C\x24\x30")  # mov [rsp+30h],rcx
    b.emit(b"\x48\x89\x54\x24\x38")  # mov [rsp+38h],rdx
    v1.emit_language_37_check(b, "orig")
    b.lea_rcx_rip(fmt)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x8B\xC8")  # mov rcx,rax
    b.jmp("tail")
    b.mark("orig")
    b.emit(b"\x48\x8B\x4C\x24\x30")  # mov rcx,[rsp+30h]
    b.mark("tail")
    b.emit(b"\x48\x8B\x54\x24\x38")  # mov rdx,[rsp+38h]
    b.emit(b"\x45\x33\xC0")  # xor r8d,r8d
    b.emit(b"\x48\x83\xC4\x28")  # add rsp,28h
    b.jmp_abs(STRING_FORMAT_ARRAY_VA)
    return b.finish()


def build_cap_helper(va: int, fmt: int) -> bytes:
    """String.Format(rcx=fmt, rdx=percent, r8=stat name) with a Korean noun-first format."""
    b = v1.X64Builder(va)
    b.emit(b"\x48\x83\xEC\x28")  # sub rsp,28h
    b.emit(b"\x48\x89\x4C\x24\x30")  # mov [rsp+30h],rcx
    b.emit(b"\x48\x89\x54\x24\x38")  # mov [rsp+38h],rdx
    b.emit(b"\x4C\x89\x44\x24\x40")  # mov [rsp+40h],r8
    v1.emit_language_37_check(b, "orig")
    b.lea_rcx_rip(fmt)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x8B\xC8")  # mov rcx,rax
    b.jmp("tail")
    b.mark("orig")
    b.emit(b"\x48\x8B\x4C\x24\x30")  # mov rcx,[rsp+30h]
    b.mark("tail")
    b.emit(b"\x48\x8B\x54\x24\x38")  # mov rdx,[rsp+38h]
    b.emit(b"\x4C\x8B\x44\x24\x40")  # mov r8,[rsp+40h]
    b.emit(b"\x45\x33\xC9")  # xor r9d,r9d
    b.emit(b"\x48\x83\xC4\x28")  # add rsp,28h
    b.jmp_abs(STRING_FORMAT_2ARGS_VA)
    return b.finish()


def build_notice_gate_helper(va: int) -> bytes:
    """rcx=UILobbySplashScreen. Show the disconnected notice unless a match is running."""
    b = v1.X64Builder(va)
    b.emit(b"\x48\x83\xEC\x28")  # sub rsp,28h
    b.emit(b"\x48\x89\x4C\x24\x30")  # mov [rsp+30h],rcx
    b.mov_rax_rip_qword(v1.UI_MANAGER_TYPE_PTR_SLOT_VA)
    b.emit(b"\x48\x85\xC0")  # test rax,rax
    b.je("show")
    b.emit(b"\x48\x8B\x80\xB8\x00\x00\x00")  # mov rax,[rax+B8h]
    b.emit(b"\x48\x85\xC0")
    b.je("show")
    b.emit(b"\x48\x8B\x40\x08")  # mov rax,[rax+8] (UIManager.Instance)
    b.emit(b"\x48\x85\xC0")
    b.je("show")
    b.emit(b"\x48\x8B\x88" + v1.u32(UI_MANAGER_LOBBY_ROOT_OFFSET))  # mov rcx,[rax+2E8h]
    b.emit(b"\x48\x85\xC9")  # test rcx,rcx
    b.je("show")
    b.emit(b"\x33\xD2")  # xor edx,edx
    b.call_abs(GAMEOBJECT_ACTIVE_SELF_VA)
    b.emit(b"\x84\xC0")  # test al,al
    b.jne("show")
    b.emit(b"\x48\x83\xC4\x28\xC3")  # add rsp,28h; ret
    b.mark("show")
    b.emit(b"\x48\x8B\x4C\x24\x30")  # mov rcx,[rsp+30h]
    b.emit(b"\x33\xD2")  # xor edx,edx
    b.emit(b"\x48\x83\xC4\x28")  # add rsp,28h
    b.jmp_abs(SHOW_DISCONNECTED_VA)
    return b.finish()


def build_match_start_helper(va: int) -> bytes:
    """rcx=UIManager. CloseLobbyUI, then take down a notice that was already on screen."""
    b = v1.X64Builder(va)
    b.emit(b"\x48\x83\xEC\x28")  # sub rsp,28h
    b.emit(b"\x48\x89\x4C\x24\x30")  # mov [rsp+30h],rcx
    b.call_abs(CLOSE_LOBBY_UI_VA)
    b.emit(b"\x48\x8B\x44\x24\x30")  # mov rax,[rsp+30h]
    b.emit(b"\x48\x8B\x80" + v1.u32(UI_MANAGER_LOBBY_OFFSET))  # mov rax,[rax+2E0h]
    b.emit(b"\x48\x85\xC0")
    b.je("done")
    b.emit(b"\x48\x8B\x48" + bytes((UI_LOBBY_SPLASH_OFFSET,)))  # mov rcx,[rax+30h]
    b.emit(b"\x48\x85\xC9")
    b.je("done")
    b.emit(b"\x33\xD2")  # xor edx,edx
    b.emit(b"\x48\x83\xC4\x28")  # add rsp,28h
    b.jmp_abs(HIDE_DISCONNECTED_VA)
    b.mark("done")
    b.emit(b"\x48\x83\xC4\x28\xC3")  # add rsp,28h; ret
    return b.finish()


def build(v1_bytes: bytes) -> tuple[bytes, list[dict], bytes]:
    if hashlib.sha256(v1_bytes).hexdigest().upper() != V1_SHA256:
        raise SystemExit("input is not the verified v1 GameAssembly.dll")
    pe = pefile.PE(data=v1_bytes, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == v1.PATCH_SECTION_NAME)
    if sec.PointerToRawData + sec.SizeOfRawData != len(v1_bytes):
        raise SystemExit(".bapko is not the last raw data in the file")
    v_used = sec.Misc_VirtualSize
    sec_va = base + sec.VirtualAddress
    raw_blob = v1_bytes[sec.PointerToRawData : sec.PointerToRawData + v_used]
    unwind_off = raw_blob.find(v1.UNWIND_ALLOC_28)
    if unwind_off < 0:
        raise SystemExit("v1 alloc unwind record not found")
    unwind_rva = sec.VirtualAddress + unwind_off

    # Lay out the new tail of the section.
    extra = bytearray(b"\0" * ((-v_used) % 16))
    cursor = lambda: v_used + len(extra)
    extra += MARKER_V2

    def cstr(text: str) -> int:
        off = cursor()
        extra.extend(text.encode("utf-8") + b"\0")
        return sec_va + off

    s_gt = cstr(">")
    s_open_b = cstr(" <b>")
    s_close = cstr("</b></color>")
    s_cap = cstr("{1} {0}%")
    s_b = cstr("<b>")
    s_dmg = cstr("<color=#{0}>{2}<b>{1}</b></color> {3}")
    extra.extend(b"\x90" * ((-cursor()) % 16))
    stat_va = sec_va + cursor()
    stat_code = build_stat_helper(stat_va, s_gt, s_open_b, s_close, s_b)
    extra += stat_code
    extra.extend(b"\x90" * ((-cursor()) % 16))
    cap_va = sec_va + cursor()
    cap_code = build_cap_helper(cap_va, s_cap)
    extra += cap_code
    extra.extend(b"\x90" * ((-cursor()) % 16))
    dmg_va = sec_va + cursor()
    dmg_code = build_damage_format_helper(dmg_va, s_dmg)
    extra += dmg_code
    extra.extend(b"\x90" * ((-cursor()) % 16))
    gate_va = sec_va + cursor()
    gate_code = build_notice_gate_helper(gate_va)
    extra += gate_code
    extra.extend(b"\x90" * ((-cursor()) % 16))
    start_va = sec_va + cursor()
    start_code = build_match_start_helper(start_va)
    extra += start_code
    helpers = ((stat_va, stat_code), (cap_va, cap_code), (dmg_va, dmg_code), (gate_va, gate_code), (start_va, start_code))

    new_vsize = v_used + len(extra)
    fa = pe.OPTIONAL_HEADER.FileAlignment
    new_raw = v1.align_up(new_vsize, fa)
    sa = pe.OPTIONAL_HEADER.SectionAlignment
    if v1.align_up(sec.VirtualAddress + new_vsize, sa) != pe.OPTIONAL_HEADER.SizeOfImage:
        raise SystemExit("section growth would change SizeOfImage")
    if new_raw < sec.SizeOfRawData:
        new_raw = sec.SizeOfRawData

    edits: list[dict] = []

    def edit(off: int, old: bytes, new: bytes, name: str) -> None:
        if v1_bytes[off : off + len(old)] != old:
            raise SystemExit(f"guard failed: {name} at {off:#x}")
        edits.append({"name": name, "offset": off, "expected": old.hex().upper(), "replacement": new.hex().upper()})

    def va_off(va: int) -> int:
        return pe.get_offset_from_rva(va - base)

    # Code edits
    va, old = FRIEND_NAME_BRANCH
    target = 0x1805885B4
    if struct.unpack_from("<i", old, 2)[0] + va + 6 != target:
        raise SystemExit("friend branch target mismatch")
    edit(va_off(va), old, v1.rel32_bytes(0xE9, va, target) + b"\x90", "friend_name_skip_char_removal")
    va, old = ITEM_STAT_MARKER
    edit(va_off(va), old, old[:5] + b"\x01\0\0\0", "item_stat_sentence_marker")
    va, old = STAT_PASS_STAT_ID
    edit(va_off(va), old, b"\x8B\xD7", "stat_string_pass_stat_id")
    edit(
        va_off(STAT_CONCAT_JMP_VA),
        v1.rel32_bytes(0xE9, STAT_CONCAT_JMP_VA, STRING_CONCAT_ARRAY_VA),
        v1.rel32_bytes(0xE9, STAT_CONCAT_JMP_VA, stat_va),
        "stat_string_concat_jump",
    )
    for i, call_va in enumerate(CAP_FORMAT_CALLS):
        edit(
            va_off(call_va),
            v1.rel32_bytes(0xE8, call_va, STRING_FORMAT_2ARGS_VA),
            v1.rel32_bytes(0xE8, call_va, cap_va),
            f"berserk_cap_format_{i}",
        )
    for i, call_va in enumerate(DAMAGE_FORMAT_CALLS):
        edit(
            va_off(call_va),
            v1.rel32_bytes(0xE8, call_va, STRING_FORMAT_ARRAY_VA),
            v1.rel32_bytes(0xE8, call_va, dmg_va),
            f"damage_fragment_format_{i}",
        )
    edit(
        va_off(DISCONNECT_NOTICE_JMP_VA),
        v1.rel32_bytes(0xE9, DISCONNECT_NOTICE_JMP_VA, SHOW_DISCONNECTED_VA),
        v1.rel32_bytes(0xE9, DISCONNECT_NOTICE_JMP_VA, gate_va),
        "disconnect_notice_gate",
    )
    edit(
        va_off(MATCH_START_CLOSE_LOBBY_CALL_VA),
        v1.rel32_bytes(0xE8, MATCH_START_CLOSE_LOBBY_CALL_VA, CLOSE_LOBBY_UI_VA),
        v1.rel32_bytes(0xE8, MATCH_START_CLOSE_LOBBY_CALL_VA, start_va),
        "match_start_hide_notice",
    )

    # Exception table: append helpers in sorted order, into existing raw slack.
    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    pdata = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata")
    if exc.VirtualAddress != pdata.VirtualAddress:
        raise SystemExit("unexpected exception directory location")
    entries = b"".join(struct.pack("<III", v - base, v - base + len(code), unwind_rva) for v, code in helpers)
    pd_off = pdata.PointerToRawData + exc.Size
    if exc.Size + len(entries) > pdata.SizeOfRawData:
        raise SystemExit("no .pdata slack left")
    last_begin = struct.unpack_from("<I", v1_bytes, pd_off - 12)[0]
    if last_begin >= stat_va - base:
        raise SystemExit(".pdata ordering would break")
    edit(pd_off, v1_bytes[pd_off : pd_off + len(entries)], entries, "pdata_append")
    if any(v1_bytes[pd_off : pd_off + len(entries)]):
        raise SystemExit(".pdata slack is not empty")
    edit(
        exc.get_field_absolute_offset("Size"),
        struct.pack("<I", exc.Size),
        struct.pack("<I", exc.Size + len(entries)),
        "exception_dir_size",
    )
    edit(
        pdata.get_file_offset() + 8,
        struct.pack("<I", pdata.Misc_VirtualSize),
        struct.pack("<I", pdata.Misc_VirtualSize + len(entries)),
        "pdata_virtual_size",
    )

    # Section header + code size
    hdr = sec.get_file_offset()
    edit(hdr + 8, struct.pack("<I", sec.Misc_VirtualSize), struct.pack("<I", new_vsize), "bapko_virtual_size")
    edit(hdr + 16, struct.pack("<I", sec.SizeOfRawData), struct.pack("<I", new_raw), "bapko_raw_size")
    delta = new_raw - sec.SizeOfRawData
    if delta:
        off = pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfCode")
        edit(off, struct.pack("<I", pe.OPTIONAL_HEADER.SizeOfCode), struct.pack("<I", pe.OPTIONAL_HEADER.SizeOfCode + delta), "size_of_code")

    # Bytes after the used part of the section.
    raw_tail_off = sec.PointerToRawData + v_used
    slack = sec.SizeOfRawData - v_used
    overwrite = bytes(extra[:slack])
    appended = bytes(extra[slack:]) + b"\0" * (new_raw - new_vsize)
    if len(overwrite) < slack:
        # Everything fits inside the old raw area.
        appended = b""
    edit(raw_tail_off, v1_bytes[raw_tail_off : raw_tail_off + len(overwrite)], overwrite, "bapko_tail")
    if any(v1_bytes[raw_tail_off : raw_tail_off + len(overwrite)]):
        raise SystemExit(".bapko slack is not empty")

    out = bytearray(v1_bytes)
    for e in edits:
        new = bytes.fromhex(e["replacement"])
        out[e["offset"] : e["offset"] + len(new)] = new
    out.extend(appended)

    # Offline validation: parse, disassemble, check helpers end in a jump.
    pe2 = pefile.PE(data=bytes(out), fast_load=True)
    if pe2.OPTIONAL_HEADER.AddressOfEntryPoint != pe.OPTIONAL_HEADER.AddressOfEntryPoint:
        raise SystemExit("entry point changed")
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    for name, (va, code) in zip(("stat", "cap", "damage", "notice_gate", "match_start"), helpers):
        insns = list(md.disasm(code, va))
        if sum(i.size for i in insns) != len(code):
            raise SystemExit(f"helper {name} does not decode cleanly")
        if insns[-1].mnemonic not in ("jmp", "ret"):
            raise SystemExit(f"helper {name} does not end in a jump or return")
    return bytes(out), edits, appended


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, required=True, help="verified v1 GameAssembly.dll")
    p.add_argument("--json", type=Path, required=True, help="edit list consumed by install.ps1")
    p.add_argument("--output", type=Path, help="optional patched DLL for inspection")
    a = p.parse_args()
    data = a.input.read_bytes()
    out, edits, appended = build(data)
    digest = hashlib.sha256(out).hexdigest().upper()
    doc = {
        "schema_version": 1,
        "input_sha256": V1_SHA256,
        "output_sha256": digest,
        "edits": edits,
        "append": appended.hex().upper(),
    }
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_bytes(out)
    print("edits", len(edits), "appended", len(appended), "sha256", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
