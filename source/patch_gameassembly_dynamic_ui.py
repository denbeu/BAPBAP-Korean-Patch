#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM


SUPPORTED_SHA256 = "75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69"
IMAGE_BASE_EXPECTED = 0x180000000
PATCH_SECTION_NAME = b".bapko"
PATCH_MARKER = b"BAPKO_UI_PATCH_V1\0"
KOREAN_LANGUAGE_SLOT = 37

# Confirmed IL2CPP/runtime addresses for the supported GameAssembly build.
UI_MANAGER_TYPE_PTR_SLOT_VA = 0x184239268
IL2CPP_STRING_NEW_VA = 0x1803B7A50
IL2CPP_STRING_NEW_UTF16_VA = 0x1803B7A70
IL2CPP_VALUE_BOX_VA = 0x1803B7DE0
STRING_FORMAT_2ARGS_VA = 0x1821E54E0
TMP_INPUTFIELD_SET_TEXT_VA = 0x1831A9F70
GET_ORD_NUM_STR_VA = 0x180C26B80
GET_ORD_NUM_STR_RESUME_VA = GET_ORD_NUM_STR_VA + 6

# The custom-lobby object layout observed in this exact build.
VIEW_PLAYERS_LOBBY_STRING_OFFSET = 0x310


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def i32(value: int) -> bytes:
    if not -(1 << 31) <= value < (1 << 31):
        raise ValueError(f"rel32 out of range: {value}")
    return struct.pack("<i", value)


def u32(value: int) -> bytes:
    return struct.pack("<I", value)


def u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def rel32_bytes(opcode: int, source_va: int, target_va: int) -> bytes:
    return bytes([opcode]) + i32(target_va - (source_va + 5))


@dataclass(frozen=True)
class TargetPatch:
    name: str
    rva: int
    expected: bytes
    replacement: bytes
    target_rva: int | None = None
    kind: str = "bytes"


class X64Builder:
    """Tiny deterministic emitter for only the instructions this patch needs."""

    def __init__(self, base_va: int) -> None:
        self.base_va = base_va
        self.data = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    @property
    def va(self) -> int:
        return self.base_va + len(self.data)

    def emit(self, data: bytes) -> None:
        self.data.extend(data)

    def mark(self, label: str) -> None:
        if label in self.labels:
            raise ValueError(f"duplicate label: {label}")
        self.labels[label] = len(self.data)

    def jcc(self, opcode_low: int, label: str) -> None:
        # 0F 8x rel32
        self.emit(bytes((0x0F, opcode_low)))
        pos = len(self.data)
        self.emit(b"\0\0\0\0")
        self.fixups.append((pos, label))

    def je(self, label: str) -> None:
        self.jcc(0x84, label)

    def jne(self, label: str) -> None:
        self.jcc(0x85, label)

    def jle(self, label: str) -> None:
        self.jcc(0x8E, label)

    def call_abs(self, target_va: int) -> None:
        source = self.va
        self.emit(rel32_bytes(0xE8, source, target_va))

    def jmp_abs(self, target_va: int) -> None:
        source = self.va
        self.emit(rel32_bytes(0xE9, source, target_va))

    def jmp(self, label: str) -> None:
        self.emit(b"\xE9")
        pos = len(self.data)
        self.emit(b"\0\0\0\0")
        self.fixups.append((pos, label))

    def mov_rax_rip_qword(self, target_va: int) -> None:
        # 48 8B 05 disp32
        source = self.va
        self.emit(b"\x48\x8B\x05" + i32(target_va - (source + 7)))

    def lea_rcx_rip(self, target_va: int) -> None:
        # 48 8D 0D disp32
        source = self.va
        self.emit(b"\x48\x8D\x0D" + i32(target_va - (source + 7)))

    def finish(self) -> bytes:
        for disp_pos, label in self.fixups:
            if label not in self.labels:
                raise ValueError(f"missing label: {label}")
            target_va = self.base_va + self.labels[label]
            next_va = self.base_va + disp_pos + 4
            self.data[disp_pos : disp_pos + 4] = i32(target_va - next_va)
        return bytes(self.data)


def emit_language_37_check(builder: X64Builder, not_korean_label: str) -> None:
    # UIManager class pointer -> static fields -> Instance -> translator -> Language.
    # Every null state safely falls back to the original behavior.
    builder.mov_rax_rip_qword(UI_MANAGER_TYPE_PTR_SLOT_VA)
    builder.emit(b"\x48\x85\xC0")  # test rax,rax
    builder.je(not_korean_label)
    builder.emit(b"\x48\x8B\x80\xB8\x00\x00\x00")  # mov rax,[rax+B8h]
    builder.emit(b"\x48\x85\xC0")
    builder.je(not_korean_label)
    builder.emit(b"\x48\x8B\x40\x08")  # mov rax,[rax+8] (UIManager.Instance)
    builder.emit(b"\x48\x85\xC0")
    builder.je(not_korean_label)
    builder.emit(b"\x48\x8B\x80\xE0\x00\x00\x00")  # mov rax,[rax+E0h] (translator)
    builder.emit(b"\x48\x85\xC0")
    builder.je(not_korean_label)
    builder.emit(b"\x83\x78\x18" + bytes((KOREAN_LANGUAGE_SLOT,)))  # cmp [rax+18h],25h
    builder.jne(not_korean_label)


def build_ordinal_helper(helper_va: int, empty_c_va: int) -> bytes:
    b = X64Builder(helper_va)
    b.emit(b"\x48\x83\xEC\x28")  # sub rsp,28h
    emit_language_37_check(b, "english")
    b.lea_rcx_rip(empty_c_va)
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x83\xC4\x28\xC3")  # add rsp,28h; ret
    b.mark("english")
    b.emit(b"\x48\x83\xC4\x28")
    # Reproduce the 6-byte original prologue before resuming at +6.
    b.emit(b"\x53\x48\x83\xEC\x20")  # push rbx; sub rsp,20h
    b.jmp_abs(GET_ORD_NUM_STR_RESUME_VA)
    return b.finish()


def build_bool_helper(helper_va: int, on_c_va: int, off_c_va: int) -> bytes:
    b = X64Builder(helper_va)
    b.emit(b"\x48\x83\xEC\x28")
    emit_language_37_check(b, "original")
    b.emit(b"\x80\x3A\x00")  # cmp byte ptr [rdx],0
    b.je("off")
    b.lea_rcx_rip(on_c_va)
    b.jmp("make")
    b.mark("off")
    b.lea_rcx_rip(off_c_va)
    b.mark("make")
    b.call_abs(IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x83\xC4\x28\xC3")
    b.mark("original")
    b.emit(b"\x48\x83\xC4\x28")
    b.jmp_abs(IL2CPP_VALUE_BOX_VA)
    return b.finish()


def build_lobby_name_helper(helper_va: int) -> bytes:
    b = X64Builder(helper_va)
    b.emit(b"\x53\x57\x48\x83\xEC\x28")  # push rbx; push rdi; sub rsp,28h
    b.emit(b"\x48\x8B\xD9")  # mov rbx,rcx (TMP_InputField*)
    b.emit(b"\x49\x8B\xF8")  # mov rdi,r8  (View_Lobby_CustomGame*)
    b.emit(b"\x48\x89\x54\x24\x20")  # mov [rsp+20h],rdx (original string)
    emit_language_37_check(b, "passthrough")
    b.emit(b"\x48\x85\xFF")  # test rdi,rdi
    b.je("passthrough")
    b.emit(b"\x48\x85\xD2")  # test rdx,rdx
    b.je("passthrough")
    b.emit(b"\x8B\x42\x10")  # mov eax,[rdx+10h] (Il2CppString length)
    b.emit(b"\x83\xF8\x08")  # cmp eax,8
    b.jle("passthrough")  # require a non-empty <name>
    # suffix_start = chars + 2*(length-8) = string + 2*length + 4
    b.emit(b"\x4C\x8D\x54\x42\x04")  # lea r10,[rdx+rax*2+4]
    b.emit(b"\x49\xBB" + u64(0x004C002000730027))  # "'s L" UTF-16LE
    b.emit(b"\x4D\x39\x1A")  # cmp [r10],r11
    b.jne("passthrough")
    b.emit(b"\x49\xBB" + u64(0x007900620062006F))  # "obby" UTF-16LE
    b.emit(b"\x4D\x39\x5A\x08")  # cmp [r10+8],r11
    b.jne("passthrough")
    b.emit(b"\x4C\x8B\x9F" + u32(VIEW_PLAYERS_LOBBY_STRING_OFFSET))  # mov r11,[rdi+310h]
    b.emit(b"\x4D\x85\xDB")
    b.je("passthrough")
    b.emit(b"\x48\x8D\x4A\x14")  # lea rcx,[rdx+14h] (UTF-16 chars)
    b.emit(b"\x83\xE8\x08")  # sub eax,8
    b.emit(b"\x8B\xD0")  # mov edx,eax
    b.call_abs(IL2CPP_STRING_NEW_UTF16_VA)
    b.emit(b"\x48\x85\xC0")
    b.je("passthrough")
    b.emit(b"\x48\x8B\x8F" + u32(VIEW_PLAYERS_LOBBY_STRING_OFFSET))  # mov rcx,[rdi+310h]
    b.emit(b"\x48\x85\xC9")
    b.je("passthrough")
    b.emit(b"\x48\x8B\xD0")  # mov rdx,rax (nickname)
    b.emit(b"\x45\x33\xC0\x45\x33\xC9")  # xor r8d,r8d; xor r9d,r9d
    b.call_abs(STRING_FORMAT_2ARGS_VA)
    b.emit(b"\x48\x85\xC0")
    b.je("passthrough")
    b.emit(b"\x48\x8B\xD0\x48\x8B\xCB\x45\x33\xC0")  # rdx=result, rcx=input, r8=0
    b.emit(b"\x48\x83\xC4\x28\x5F\x5B")
    b.jmp_abs(TMP_INPUTFIELD_SET_TEXT_VA)
    b.mark("passthrough")
    b.emit(b"\x48\x8B\x54\x24\x20")  # restore original string
    b.emit(b"\x48\x8B\xCB\x45\x33\xC0")
    b.emit(b"\x48\x83\xC4\x28\x5F\x5B")
    b.jmp_abs(TMP_INPUTFIELD_SET_TEXT_VA)
    return b.finish()


UNWIND_ALLOC_28 = bytes.fromhex("0104010004420000")
UNWIND_LOBBY = bytes.fromhex("010603000642027001300000")


def section_name(section: Any) -> str:
    return section.Name.rstrip(b"\0").decode("ascii", errors="replace")


def section_for_rva(pe: pefile.PE, rva: int) -> Any | None:
    for section in pe.sections:
        start = section.VirtualAddress
        end = start + max(section.Misc_VirtualSize, section.SizeOfRawData)
        if start <= rva < end:
            return section
    return None


def executable_rva(pe: pefile.PE, rva: int) -> bool:
    section = section_for_rva(pe, rva)
    return bool(section and (section.Characteristics & 0x20000000))


def import_fingerprint(pe: pefile.PE) -> list[dict[str, Any]]:
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for desc in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        entries = []
        for item in desc.imports:
            entries.append(
                {
                    "name": item.name.decode(errors="replace") if item.name else None,
                    "ordinal": item.ordinal,
                    "hint": item.hint,
                }
            )
        result.append(
            {
                "dll": desc.dll.decode(errors="replace"),
                "entries": entries,
            }
        )
    return result


def build_patch_payload(section_rva: int, image_base: int) -> tuple[bytes, dict[str, Any]]:
    section_va = image_base + section_rva
    payload = bytearray(b"\0" * 0x40)
    payload[0 : len(PATCH_MARKER)] = PATCH_MARKER
    empty_off = 0x20
    on_off = 0x28
    off_off = 0x30
    payload[empty_off : empty_off + 1] = b"\0"
    payload[on_off : on_off + len("켬".encode("utf-8")) + 1] = "켬".encode("utf-8") + b"\0"
    payload[off_off : off_off + len("끔".encode("utf-8")) + 1] = "끔".encode("utf-8") + b"\0"

    def append_aligned(data: bytes, alignment: int = 16) -> int:
        while len(payload) % alignment:
            payload.append(0x90 if alignment == 16 else 0)
        offset = len(payload)
        payload.extend(data)
        return offset

    ordinal_off = align_up(len(payload), 16)
    if len(payload) < ordinal_off:
        payload.extend(b"\x90" * (ordinal_off - len(payload)))
    ordinal = build_ordinal_helper(section_va + ordinal_off, section_va + empty_off)
    payload.extend(ordinal)

    bool_off = align_up(len(payload), 16)
    payload.extend(b"\x90" * (bool_off - len(payload)))
    bool_code = build_bool_helper(section_va + bool_off, section_va + on_off, section_va + off_off)
    payload.extend(bool_code)

    lobby_off = align_up(len(payload), 16)
    payload.extend(b"\x90" * (lobby_off - len(payload)))
    lobby_code = build_lobby_name_helper(section_va + lobby_off)
    payload.extend(lobby_code)

    xdata_off = align_up(len(payload), 4)
    payload.extend(b"\0" * (xdata_off - len(payload)))
    alloc_unwind_off = xdata_off
    payload.extend(UNWIND_ALLOC_28)
    lobby_unwind_off = align_up(len(payload), 4)
    payload.extend(b"\0" * (lobby_unwind_off - len(payload)))
    payload.extend(UNWIND_LOBBY)

    meta = {
        "marker_rva": section_rva,
        "strings": {
            "empty_c_rva": section_rva + empty_off,
            "on_utf8_rva": section_rva + on_off,
            "off_utf8_rva": section_rva + off_off,
        },
        "helpers": {
            "ordinal": {
                "rva": section_rva + ordinal_off,
                "size": len(ordinal),
                "unwind_rva": section_rva + alloc_unwind_off,
            },
            "boolean": {
                "rva": section_rva + bool_off,
                "size": len(bool_code),
                "unwind_rva": section_rva + alloc_unwind_off,
            },
            "lobby_name": {
                "rva": section_rva + lobby_off,
                "size": len(lobby_code),
                "unwind_rva": section_rva + lobby_unwind_off,
            },
        },
        "xdata": {
            "alloc_28_rva": section_rva + alloc_unwind_off,
            "lobby_rva": section_rva + lobby_unwind_off,
        },
    }
    return bytes(payload), meta


def make_runtime_functions(meta: dict[str, Any]) -> bytes:
    entries = []
    for name in ("ordinal", "boolean", "lobby_name"):
        helper = meta["helpers"][name]
        begin = helper["rva"]
        end = begin + helper["size"]
        entries.append((begin, end, helper["unwind_rva"]))
    entries.sort()
    return b"".join(struct.pack("<III", *entry) for entry in entries)


def make_target_patches(image_base: int, meta: dict[str, Any]) -> list[TargetPatch]:
    ordinal_helper_va = image_base + meta["helpers"]["ordinal"]["rva"]
    bool_helper_va = image_base + meta["helpers"]["boolean"]["rva"]
    lobby_helper_va = image_base + meta["helpers"]["lobby_name"]["rva"]
    return [
        TargetPatch(
            "ordinal_getordnumstr_detour",
            GET_ORD_NUM_STR_VA - image_base,
            bytes.fromhex("40534883EC20"),
            rel32_bytes(0xE9, GET_ORD_NUM_STR_VA, ordinal_helper_va) + b"\x90",
            meta["helpers"]["ordinal"]["rva"],
            "jmp",
        ),
        TargetPatch(
            "lobby_name_pass_view_context",
            0x18053247D - image_base,
            bytes.fromhex("4533C0"),
            bytes.fromhex("4C8BC6"),  # mov r8,rsi
            None,
            "context",
        ),
        TargetPatch(
            "lobby_name_display_call",
            0x180532486 - image_base,
            bytes.fromhex("E8E57AC702"),
            rel32_bytes(0xE8, 0x180532486, lobby_helper_va),
            meta["helpers"]["lobby_name"]["rva"],
            "call",
        ),
        TargetPatch(
            "lobby_bool_allow_team_edit",
            0x180532BED - image_base,
            bytes.fromhex("E8EE51E8FF"),
            rel32_bytes(0xE8, 0x180532BED, bool_helper_va),
            meta["helpers"]["boolean"]["rva"],
            "call",
        ),
        TargetPatch(
            "lobby_bool_force_random",
            0x180532C46 - image_base,
            bytes.fromhex("E89551E8FF"),
            rel32_bytes(0xE8, 0x180532C46, bool_helper_va),
            meta["helpers"]["boolean"]["rva"],
            "call",
        ),
        TargetPatch(
            "lobby_bool_show_characters",
            0x180532C9F - image_base,
            bytes.fromhex("E83C51E8FF"),
            rel32_bytes(0xE8, 0x180532C9F, bool_helper_va),
            meta["helpers"]["boolean"]["rva"],
            "call",
        ),
    ]


def add_patch_section_and_apply(original: bytes) -> tuple[bytes, dict[str, Any]]:
    pe = pefile.PE(data=original, fast_load=False)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    if image_base != IMAGE_BASE_EXPECTED:
        raise RuntimeError(f"unexpected ImageBase: 0x{image_base:X}")
    if pe.get_overlay_data_start_offset() is not None:
        raise RuntimeError("unsupported PE overlay present")
    if any(section.Name.rstrip(b"\0") == PATCH_SECTION_NAME for section in pe.sections):
        raise RuntimeError("DLL already contains .bapko patch section")

    file_alignment = pe.OPTIONAL_HEADER.FileAlignment
    section_alignment = pe.OPTIONAL_HEADER.SectionAlignment
    last = pe.sections[-1]
    new_rva = align_up(
        last.VirtualAddress + max(last.Misc_VirtualSize, last.SizeOfRawData),
        section_alignment,
    )
    payload, meta = build_patch_payload(new_rva, image_base)
    new_raw_size = align_up(len(payload), file_alignment)
    new_raw_ptr = align_up(len(original), file_alignment)

    section_table_end = pe.sections[-1].get_file_offset() + 40
    new_section_header_off = section_table_end
    if new_section_header_off + 40 > pe.OPTIONAL_HEADER.SizeOfHeaders:
        raise RuntimeError("no PE header room for .bapko section header")
    if any(original[new_section_header_off : new_section_header_off + 40]):
        raise RuntimeError("new section header slot is not zero-filled")

    exception_dir = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    old_exception_rva = exception_dir.VirtualAddress
    old_exception_size = exception_dir.Size
    pdata = section_for_rva(pe, old_exception_rva)
    if pdata is None or section_name(pdata) != ".pdata":
        raise RuntimeError("exception directory is not backed by .pdata")
    if old_exception_rva != pdata.VirtualAddress:
        raise RuntimeError("unexpected exception directory offset within .pdata")
    runtime_functions = make_runtime_functions(meta)
    pdata_append_rva = old_exception_rva + old_exception_size
    pdata_append_off = pdata.PointerToRawData + old_exception_size
    pdata_raw_end = pdata.PointerToRawData + pdata.SizeOfRawData
    if pdata_append_off + len(runtime_functions) > pdata_raw_end:
        raise RuntimeError("insufficient .pdata raw slack for patch unwind entries")
    if any(original[pdata_append_off : pdata_append_off + len(runtime_functions)]):
        raise RuntimeError(".pdata append area is not zero-filled")

    # Ensure appending keeps the exception function table sorted by BeginAddress.
    if old_exception_size < 12 or old_exception_size % 12:
        raise RuntimeError("unexpected exception directory size")
    last_old_begin, _, _ = struct.unpack_from(
        "<III", original, pdata.PointerToRawData + old_exception_size - 12
    )
    first_new_begin = struct.unpack_from("<I", runtime_functions, 0)[0]
    if first_new_begin <= last_old_begin:
        raise RuntimeError("new runtime functions would break .pdata sort order")

    patches = make_target_patches(image_base, meta)
    for patch in patches:
        off = pe.get_offset_from_rva(patch.rva)
        actual = original[off : off + len(patch.expected)]
        if actual != patch.expected:
            raise RuntimeError(
                f"target-byte guard failed for {patch.name} at RVA 0x{patch.rva:X}: "
                f"expected {patch.expected.hex()} got {actual.hex()}"
            )

    data = bytearray(original)
    if len(data) < new_raw_ptr:
        data.extend(b"\0" * (new_raw_ptr - len(data)))
    data.extend(payload)
    if len(payload) < new_raw_size:
        data.extend(b"\0" * (new_raw_size - len(payload)))

    # New section header: RX code, deliberately not writable.
    characteristics = 0x60000020  # CNT_CODE | MEM_EXECUTE | MEM_READ
    section_header = struct.pack(
        "<8sIIIIIIHHI",
        PATCH_SECTION_NAME.ljust(8, b"\0"),
        len(payload),
        new_rva,
        new_raw_size,
        new_raw_ptr,
        0,
        0,
        0,
        0,
        characteristics,
    )
    data[new_section_header_off : new_section_header_off + 40] = section_header

    # PE header bookkeeping.
    struct.pack_into(
        "<H",
        data,
        pe.FILE_HEADER.get_field_absolute_offset("NumberOfSections"),
        pe.FILE_HEADER.NumberOfSections + 1,
    )
    struct.pack_into(
        "<I",
        data,
        pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfImage"),
        align_up(new_rva + len(payload), section_alignment),
    )
    struct.pack_into(
        "<I",
        data,
        pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfCode"),
        pe.OPTIONAL_HEADER.SizeOfCode + new_raw_size,
    )

    # Extend .pdata only into pre-existing raw slack and append the new unwind records.
    data[pdata_append_off : pdata_append_off + len(runtime_functions)] = runtime_functions
    struct.pack_into(
        "<I", data, pdata.get_file_offset() + 8, pdata.Misc_VirtualSize + len(runtime_functions)
    )
    struct.pack_into(
        "<I",
        data,
        exception_dir.get_field_absolute_offset("Size"),
        old_exception_size + len(runtime_functions),
    )

    for patch in patches:
        off = pe.get_offset_from_rva(patch.rva)
        data[off : off + len(patch.replacement)] = patch.replacement

    build_meta = {
        **meta,
        "section": {
            "name": PATCH_SECTION_NAME.decode(),
            "rva": new_rva,
            "raw_offset": new_raw_ptr,
            "virtual_size": len(payload),
            "raw_size": new_raw_size,
            "characteristics": characteristics,
        },
        "pdata": {
            "section_rva": pdata.VirtualAddress,
            "original_virtual_size": pdata.Misc_VirtualSize,
            "new_virtual_size": pdata.Misc_VirtualSize + len(runtime_functions),
            "original_exception_size": old_exception_size,
            "new_exception_size": old_exception_size + len(runtime_functions),
            "append_rva": pdata_append_rva,
            "append_raw_offset": pdata_append_off,
            "added_runtime_function_bytes": runtime_functions.hex().upper(),
            "last_original_begin_rva": last_old_begin,
        },
        "patches": patches,
        "original_file_size": len(original),
        "patched_file_size": len(data),
    }
    return bytes(data), build_meta


def diff_ranges(a: bytes, b: bytes, common_length: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(common_length):
        different = a[i] != b[i]
        if different and start is None:
            start = i
        elif not different and start is not None:
            ranges.append((start, i))
            start = None
    if start is not None:
        ranges.append((start, common_length))
    return ranges


def validate_patch(original: bytes, patched: bytes, meta: dict[str, Any]) -> dict[str, Any]:
    original_pe = pefile.PE(data=original, fast_load=False)
    patched_pe = pefile.PE(data=patched, fast_load=False)
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    checks["pe_parse"] = True
    checks["entry_point_unchanged"] = (
        original_pe.OPTIONAL_HEADER.AddressOfEntryPoint
        == patched_pe.OPTIONAL_HEADER.AddressOfEntryPoint
    )
    checks["image_base_unchanged"] = (
        original_pe.OPTIONAL_HEADER.ImageBase == patched_pe.OPTIONAL_HEADER.ImageBase
    )
    checks["section_count_plus_one"] = (
        patched_pe.FILE_HEADER.NumberOfSections == original_pe.FILE_HEADER.NumberOfSections + 1
    )

    original_sections = []
    patched_sections = []
    for section in original_pe.sections:
        original_sections.append(
            (
                section_name(section),
                section.VirtualAddress,
                section.SizeOfRawData,
                section.PointerToRawData,
                section.Characteristics,
            )
        )
    for section in patched_pe.sections[: len(original_pe.sections)]:
        patched_sections.append(
            (
                section_name(section),
                section.VirtualAddress,
                section.SizeOfRawData,
                section.PointerToRawData,
                section.Characteristics,
            )
        )
    checks["existing_sections_preserved"] = original_sections == patched_sections

    bapko = next(
        (s for s in patched_pe.sections if s.Name.rstrip(b"\0") == PATCH_SECTION_NAME), None
    )
    checks["bapko_section_exists"] = bapko is not None
    if bapko is None:
        raise RuntimeError("validation: .bapko section missing")
    checks["bapko_rva_aligned"] = (
        bapko.VirtualAddress % patched_pe.OPTIONAL_HEADER.SectionAlignment == 0
    )
    checks["bapko_raw_aligned"] = (
        bapko.PointerToRawData % patched_pe.OPTIONAL_HEADER.FileAlignment == 0
    )
    checks["bapko_rx_not_writable"] = bool(bapko.Characteristics & 0x20000000) and bool(
        bapko.Characteristics & 0x40000000
    ) and not bool(bapko.Characteristics & 0x80000000)
    checks["patch_marker"] = (
        patched[bapko.PointerToRawData : bapko.PointerToRawData + len(PATCH_MARKER)]
        == PATCH_MARKER
    )
    expected_size_of_image = align_up(
        bapko.VirtualAddress + bapko.Misc_VirtualSize,
        patched_pe.OPTIONAL_HEADER.SectionAlignment,
    )
    checks["size_of_image"] = patched_pe.OPTIONAL_HEADER.SizeOfImage == expected_size_of_image

    # Imports must remain semantically identical and their directory unchanged.
    orig_import_dir = original_pe.OPTIONAL_HEADER.DATA_DIRECTORY[1]
    new_import_dir = patched_pe.OPTIONAL_HEADER.DATA_DIRECTORY[1]
    checks["import_directory_unchanged"] = (
        orig_import_dir.VirtualAddress == new_import_dir.VirtualAddress
        and orig_import_dir.Size == new_import_dir.Size
        and import_fingerprint(original_pe) == import_fingerprint(patched_pe)
    )

    # Exception table: original bytes stay byte-for-byte identical; only 3 entries are appended.
    orig_exc = original_pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    new_exc = patched_pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    orig_pdata = section_for_rva(original_pe, orig_exc.VirtualAddress)
    new_pdata = section_for_rva(patched_pe, new_exc.VirtualAddress)
    if orig_pdata is None or new_pdata is None:
        raise RuntimeError("validation: .pdata missing")
    orig_exc_bytes = original[
        orig_pdata.PointerToRawData : orig_pdata.PointerToRawData + orig_exc.Size
    ]
    new_exc_prefix = patched[
        new_pdata.PointerToRawData : new_pdata.PointerToRawData + orig_exc.Size
    ]
    checks["exception_original_table_preserved"] = orig_exc_bytes == new_exc_prefix
    checks["exception_size_extended_by_three"] = new_exc.Size == orig_exc.Size + 36
    appended = patched[
        new_pdata.PointerToRawData + orig_exc.Size : new_pdata.PointerToRawData + new_exc.Size
    ]
    checks["exception_appended_bytes"] = (
        appended.hex().upper() == meta["pdata"]["added_runtime_function_bytes"]
    )

    runtime_entries = [struct.unpack_from("<III", appended, i) for i in range(0, len(appended), 12)]
    helper_names = ("ordinal", "boolean", "lobby_name")
    unwind_checks = []
    for helper_name, entry in zip(helper_names, runtime_entries):
        helper = meta["helpers"][helper_name]
        expected = (
            helper["rva"],
            helper["rva"] + helper["size"],
            helper["unwind_rva"],
        )
        unwind_checks.append(entry == expected)
    checks["runtime_function_entries"] = all(unwind_checks)
    checks["runtime_function_sorted"] = all(
        runtime_entries[i][0] < runtime_entries[i + 1][0]
        for i in range(len(runtime_entries) - 1)
    ) and meta["pdata"]["last_original_begin_rva"] < runtime_entries[0][0]

    # Validate xdata bytes and that all helper ranges are executable.
    alloc_unwind_off = patched_pe.get_offset_from_rva(meta["xdata"]["alloc_28_rva"])
    lobby_unwind_off = patched_pe.get_offset_from_rva(meta["xdata"]["lobby_rva"])
    checks["unwind_alloc28_bytes"] = (
        patched[alloc_unwind_off : alloc_unwind_off + len(UNWIND_ALLOC_28)] == UNWIND_ALLOC_28
    )
    checks["unwind_lobby_bytes"] = (
        patched[lobby_unwind_off : lobby_unwind_off + len(UNWIND_LOBBY)] == UNWIND_LOBBY
    )
    checks["helper_ranges_executable"] = all(
        executable_rva(patched_pe, meta["helpers"][name]["rva"])
        for name in helper_names
    )

    # Verify every guarded patch byte and every patched direct branch/call target.
    patch_results = []
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    for patch in meta["patches"]:
        original_off = original_pe.get_offset_from_rva(patch.rva)
        patched_off = patched_pe.get_offset_from_rva(patch.rva)
        original_actual = original[original_off : original_off + len(patch.expected)]
        patched_actual = patched[patched_off : patched_off + len(patch.replacement)]
        ok_original = original_actual == patch.expected
        ok_patched = patched_actual == patch.replacement
        target_ok = True
        decoded_target = None
        if patch.kind in ("call", "jmp"):
            va = patched_pe.OPTIONAL_HEADER.ImageBase + patch.rva
            insns = list(md.disasm(patched_actual, va, count=1))
            if len(insns) != 1 or not insns[0].operands or insns[0].operands[0].type != X86_OP_IMM:
                target_ok = False
            else:
                decoded_target = insns[0].operands[0].imm
                expected_target = patched_pe.OPTIONAL_HEADER.ImageBase + int(patch.target_rva)
                target_ok = decoded_target == expected_target and executable_rva(
                    patched_pe, decoded_target - patched_pe.OPTIONAL_HEADER.ImageBase
                )
        patch_results.append(
            {
                "name": patch.name,
                "rva": f"0x{patch.rva:X}",
                "original_bytes": patch.expected.hex().upper(),
                "patched_bytes": patch.replacement.hex().upper(),
                "original_guard": ok_original,
                "patched_match": ok_patched,
                "decoded_target_va": f"0x{decoded_target:X}" if decoded_target is not None else None,
                "branch_target_ok": target_ok,
            }
        )
    checks["target_byte_guards"] = all(item["original_guard"] for item in patch_results)
    checks["patched_bytes"] = all(item["patched_match"] for item in patch_results)
    checks["patched_branch_targets"] = all(item["branch_target_ok"] for item in patch_results)

    # Inspect all direct calls/jumps emitted inside helper ranges. Every immediate target must be executable.
    helper_branch_details = []
    helper_branches_ok = True
    for helper_name in helper_names:
        helper = meta["helpers"][helper_name]
        helper_off = patched_pe.get_offset_from_rva(helper["rva"])
        helper_bytes = patched[helper_off : helper_off + helper["size"]]
        helper_va = patched_pe.OPTIONAL_HEADER.ImageBase + helper["rva"]
        for insn in md.disasm(helper_bytes, helper_va):
            if insn.mnemonic.startswith("j") or insn.mnemonic == "call":
                if insn.operands and insn.operands[0].type == X86_OP_IMM:
                    target_va = insn.operands[0].imm
                    target_rva = target_va - patched_pe.OPTIONAL_HEADER.ImageBase
                    is_exec = executable_rva(patched_pe, target_rva)
                    helper_branch_details.append(
                        {
                            "helper": helper_name,
                            "source_va": f"0x{insn.address:X}",
                            "mnemonic": insn.mnemonic,
                            "target_va": f"0x{target_va:X}",
                            "target_executable": is_exec,
                        }
                    )
                    helper_branches_ok &= is_exec
    checks["helper_branch_targets_executable"] = helper_branches_ok

    # Only explicitly approved existing-file ranges may differ before the appended section data.
    allowed_ranges: list[tuple[int, int, str]] = []
    allowed_ranges.append(
        (
            original_pe.FILE_HEADER.get_field_absolute_offset("NumberOfSections"),
            original_pe.FILE_HEADER.get_field_absolute_offset("NumberOfSections") + 2,
            "NumberOfSections",
        )
    )
    for field, size in (("SizeOfCode", 4), ("SizeOfImage", 4)):
        off = original_pe.OPTIONAL_HEADER.get_field_absolute_offset(field)
        allowed_ranges.append((off, off + size, field))
    exc_size_off = original_pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].get_field_absolute_offset("Size")
    allowed_ranges.append((exc_size_off, exc_size_off + 4, "ExceptionDirectory.Size"))
    allowed_ranges.append(
        (
            original_pe.sections[-1].get_file_offset() + 40,
            original_pe.sections[-1].get_file_offset() + 80,
            ".bapko section header",
        )
    )
    orig_pdata_vsize_off = orig_pdata.get_file_offset() + 8
    allowed_ranges.append((orig_pdata_vsize_off, orig_pdata_vsize_off + 4, ".pdata VirtualSize"))
    allowed_ranges.append(
        (
            orig_pdata.PointerToRawData + orig_exc.Size,
            orig_pdata.PointerToRawData + orig_exc.Size + 36,
            "appended RUNTIME_FUNCTION entries",
        )
    )
    for patch in meta["patches"]:
        off = original_pe.get_offset_from_rva(patch.rva)
        allowed_ranges.append((off, off + len(patch.replacement), patch.name))

    diffs = diff_ranges(original, patched, len(original))
    unexpected_diffs = []
    for start, end in diffs:
        covered = any(start >= a and end <= b for a, b, _ in allowed_ranges)
        if not covered:
            unexpected_diffs.append((start, end))
    checks["no_unexpected_original_range_changes"] = not unexpected_diffs

    details["patches"] = patch_results
    details["helper_branches"] = helper_branch_details
    details["diff_ranges_before_appended_section"] = [
        {"start": f"0x{s:X}", "end": f"0x{e:X}"} for s, e in diffs
    ]
    details["unexpected_diff_ranges"] = [
        {"start": f"0x{s:X}", "end": f"0x{e:X}"} for s, e in unexpected_diffs
    ]
    details["runtime_function_entries"] = [
        {
            "begin_rva": f"0x{a:X}",
            "end_rva": f"0x{b:X}",
            "unwind_rva": f"0x{c:X}",
        }
        for a, b, c in runtime_entries
    ]

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "passed": not failed,
        "checks": checks,
        "failed_checks": failed,
        "details": details,
    }


def serializable_meta(meta: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in meta.items():
        if key == "patches":
            result[key] = [
                {
                    "name": p.name,
                    "rva": f"0x{p.rva:X}",
                    "original_bytes": p.expected.hex().upper(),
                    "patched_bytes": p.replacement.hex().upper(),
                    "target_rva": f"0x{p.target_rva:X}" if p.target_rva is not None else None,
                    "kind": p.kind,
                }
                for p in value
            ]
        elif isinstance(value, dict):
            result[key] = serializable_meta(value)
        elif isinstance(value, int) and (key.endswith("rva") or key.endswith("offset")):
            result[key] = f"0x{value:X}"
        else:
            result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch the supported BAPBAP GameAssembly dynamic Korean UI paths offline."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("build/GameAssembly.ko-patched.dll"))
    parser.add_argument(
        "--report", type=Path, default=Path("reports/gameassembly_patch_report.json")
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    report_path = args.report.resolve()
    if input_path == output_path:
        raise SystemExit("refusing to overwrite the input GameAssembly.dll")
    if not input_path.is_file():
        raise SystemExit(f"input does not exist: {input_path}")

    original = input_path.read_bytes()
    original_hash = sha256_bytes(original)

    # Identify a previously patched DLL before the supported-hash rejection message.
    try:
        probe = pefile.PE(data=original, fast_load=True)
        if any(section.Name.rstrip(b"\0") == PATCH_SECTION_NAME for section in probe.sections):
            raise SystemExit("refusing duplicate application: input already contains .bapko")
    except pefile.PEFormatError as exc:
        raise SystemExit(f"input is not a valid PE: {exc}") from exc

    if original_hash != SUPPORTED_SHA256:
        raise SystemExit(
            "unsupported GameAssembly.dll SHA-256: "
            f"{original_hash}; expected {SUPPORTED_SHA256}"
        )

    patched, meta = add_patch_section_and_apply(original)
    validation = validate_patch(original, patched, meta)
    if not validation["passed"]:
        raise SystemExit(
            "offline validation failed: " + ", ".join(validation["failed_checks"])
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_bytes(patched)
    # Reopen from disk before publishing the final filename.
    reopened = temp_path.read_bytes()
    disk_validation = validate_patch(original, reopened, meta)
    if not disk_validation["passed"]:
        temp_path.unlink(missing_ok=True)
        raise SystemExit(
            "disk reopen validation failed: " + ", ".join(disk_validation["failed_checks"])
        )
    os.replace(temp_path, output_path)

    original_pe = pefile.PE(data=original, fast_load=True)
    patched_pe = pefile.PE(data=patched, fast_load=True)
    bapko = next(s for s in patched_pe.sections if s.Name.rstrip(b"\0") == PATCH_SECTION_NAME)
    report = {
        "schema_version": 1,
        "scope": "offline GameAssembly dynamic Korean UI patch only",
        "input": str(input_path),
        "output": str(output_path),
        "original_sha256": original_hash,
        "patched_sha256": sha256_bytes(patched),
        "original_size": len(original),
        "patched_size": len(patched),
        "entry_point_rva_original": f"0x{original_pe.OPTIONAL_HEADER.AddressOfEntryPoint:X}",
        "entry_point_rva_patched": f"0x{patched_pe.OPTIONAL_HEADER.AddressOfEntryPoint:X}",
        "added_section": {
            "name": section_name(bapko),
            "rva": f"0x{bapko.VirtualAddress:X}",
            "raw_offset": f"0x{bapko.PointerToRawData:X}",
            "virtual_size": f"0x{bapko.Misc_VirtualSize:X}",
            "raw_size": f"0x{bapko.SizeOfRawData:X}",
            "characteristics": f"0x{bapko.Characteristics:X}",
            "readable": bool(bapko.Characteristics & 0x40000000),
            "writable": bool(bapko.Characteristics & 0x80000000),
            "executable": bool(bapko.Characteristics & 0x20000000),
        },
        "build": serializable_meta(meta),
        "validation": disk_validation,
        "unresolved_risks": [
            "Offline structural validation cannot prove runtime behavior without launching the game.",
            "Locale detection intentionally depends on the supported build's UIManager static-field layout and translator field offsets, guarded by the exact source SHA-256.",
            "Lobby-name conversion only matches a non-empty managed string ending exactly with \"'s Lobby\"; all other names pass through unchanged.",
        ],
        "production_files_modified": False,
        "game_launched": False,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"original sha256: {original_hash}")
    print(f"patched  sha256: {report['patched_sha256']}")
    print(
        f".bapko RVA 0x{bapko.VirtualAddress:X} raw 0x{bapko.PointerToRawData:X} "
        f"vsize 0x{bapko.Misc_VirtualSize:X} rawsize 0x{bapko.SizeOfRawData:X}"
    )
    print(f"offline validation: PASS ({len(disk_validation['checks'])} checks)")
    print(f"output: {output_path}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
