#!/usr/bin/env python3
"""Optional mod: hold X in a match to see the current character's stats in the game's tooltip window.

Applied on top of the Korean patch v2 GameAssembly.dll, and it only reads stats. The patch tool and
install.ps1 -StatPanel apply payload/v2/stat_panel_edits.json, which this script writes:

    python stat_panel.py --game-dir "F:\\...\\BAPBAP" --write-edits payload/v2/stat_panel_edits.json

For development it can also patch a game folder directly:

    python stat_panel.py --game-dir "F:\\...\\BAPBAP" --install
    python stat_panel.py --game-dir "F:\\...\\BAPBAP" --remove
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import struct
import sys
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

_src = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("patch_gameassembly_dynamic_ui", _src / "patch_gameassembly_dynamic_ui.py")
v1 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v1
_spec.loader.exec_module(v1)

BASE_SHA256 = "775735C873581D8BDEA90AD18615FAA44226D7A3F44A0486009852BD7C49BB09"
V2_HELPER_COUNT = 5
KEY_X = 120

# Hook: the first call in UIManager.Update, which runs every frame.
HOOK_CALL_VA = 0x1806830B4
SCREEN_WIDTH_VA = 0x18326C270
SCREEN_HEIGHT_VA = 0x18326C190
INPUT_GET_KEY_VA = 0x1832FE820
INPUT_GET_KEY_UP_VA = 0x1832FE860
INPUT_GET_KEY_DOWN_VA = 0x1832FE7E0
TIME_FRAME_COUNT_VA = 0x183296910
BUILD_ITEM_STAT_STR_VA = 0x180B43360
TOOLTIP_SHOW_VA = 0x18057C130
TOOLTIP_HIDE_VA = 0x18057C0A0
FADE_IN_INSTANT_VA = 0x18051DCF0
GET_MODIFIED_DAMAGE_VA = 0x180884B70
INT32_TO_STRING_VA = 0x18238F910
STRING_REPLACE_VA = 0x1821E9430

CHAR_ABILITIES_LIST = 0xB0
KLASS_GET_TOOLTIP_DESCRIPTION = 0x3B8  # vtable start 0x138 + slot 40 * 16
BASIC_HIT_SLOTS = 3

# Slot 0 ability of every playable character. An ability class is identified by its own
# GetTooltipDescription, and each hit is (damage field, damage scaling field) as read by the code that
# really deals the damage, because some tooltips use other fields or leave hits out.
BASIC_ATTACKS = (
    (0x1807653F0, ((0x1F0, 0x1F4),)),                           # Kitsu, ArrowAbility
    (0x1807E4EF0, ((0x214, 0x218), (0x21C, 0x218))),            # Skinny, AssassinMeleeAbility: both hits use damage1Scaling
    (0x18076E5B0, ((0x1C4, 0x1C8),)),                           # Kat, CatThrowAbility
    (0x18081A210, ((0x1C0, 0x1C4),)),                           # Teevee, DigitalProjectileAbility
    (0x1807469F0, ((0x1C8, 0x1CC), (0x1EC, 0x1F0))),            # Eve, EveShardAbility: shot, shard
    (0x180772880, ((0x1C0, 0x1C4),)),                           # Kiddo, FireAttackAbility
    (0x180758B70, ((0x1D8, 0x1DC), (0x1E4, 0x1E8), (0x1F0, 0x1F4))),  # Froggy, FroggyMeleeAbility
    (0x18075E140, ((0x1D0, 0x1D4), (0x1DC, 0x1E0), (0x1E8, 0x1EC))),  # Jiro, JiroPunchAbility
    (0x1808092D0, ((0x1FC, 0x200), (0x204, 0x208), (0x20C, 0x210))),  # Sofia, KatanaMeleeAbility
    (0x1807A2500, ((0x1D0, 0x1D4), (0x1DC, 0x1E0), (0x1E8, 0x1EC))),  # Mech, MechSlashAbility: 2 hits, dash
    (0x18074D150, ((0x1CC, 0x1D0), (0x1D8, 0x1DC), (0x1E4, 0x1E8))),  # Chuck, Blitz, PunchSequenceAbility
    (0x180830F20, ((0x1E8, 0x1F0), (0x1EC, 0x1F0))),            # Zook, RocketAbility: hit, explosion
    (0x1807BFCF0, ((0x1CC, 0x1D0), (0x1D8, 0x1DC))),            # Rocky, RockyPunchAbility
    (0x180704B70, ((0x1D8, 0x1DC),)),                           # Anna, RunNGunAbility
    (0x180722D30, ((0x1DC, 0x1E0),)),                           # Bishop, SpriestTetherAbility
    (0x1807F6B30, ((0x200, 0x204), (0x20C, 0x210), (0x218, 0x21C))),  # Sashimi, WidePunchAbility
)

UI_MANAGER_CHAT = 0x30
UI_MANAGER_TOOLTIP = 0x70
UI_CHAT_IS_FOCUSED = 0xE8
UI_TOOLTIP_ELEMENT = 0x48
UI_TOOLTIP_ELEMENT_FADE = 0x80
REFRESH_FRAME_MASK = 15  # rebuild the text on key down and then every 16 frames

ABILITIES, HURTBOX, MOVE, REGEN = 0xA8, 0x98, 0x88, 0xC8  # EntityManager component fields

BASIC_ATTACK_ROW = 0xFF
DMG_PERCENT_ROW_INDEX = 1

# BAPBAP.Items.Stats value, component, field, field is int, shown value = field * a + b.
# Attack speed, cooldown reduction, and damage % start at 1.0, so 1.0 is removed to show the bonus.
# Defense starts at 1.0 as a damage-taken multiplier and items subtract from it.
STATS = (
    (1, ABILITIES, 0xF4, False, 1.0, 0.0),    # Dmg
    (17, ABILITIES, 0x114, False, 1.0, -1.0),  # DmgPercent
    (BASIC_ATTACK_ROW, 0, 0, False, 0.0, 0.0),
    (7, ABILITIES, 0xF8, False, 1.0, -1.0),    # AtkSpeed
    (2, MOVE, 0xF8, False, 1.0, 0.0),          # MoveSpeed
    (3, ABILITIES, 0xFC, False, 1.0, -1.0),    # CooldownReduction
    (4, ABILITIES, 0x100, False, 1.0, 0.0),    # CritChance
    (5, ABILITIES, 0x104, False, 1.0, 0.0),    # CritDmg
    (6, ABILITIES, 0x108, False, 1.0, 0.0),    # Lifesteal
    (10, HURTBOX, 0x11C, True, 1.0, 0.0),      # Hp (max)
    (11, REGEN, 0x94, True, 1.0, 0.0),         # HpRegen
    (13, HURTBOX, 0x13C, False, -1.0, 1.0),    # Defense
    (8, HURTBOX, 0x12C, False, 1.0, 0.0),      # Thorns
    (14, ABILITIES, 0x10C, False, 1.0, 0.0),   # Shred
    (15, ABILITIES, 0x110, False, 1.0, 0.0),   # Luck
)
TITLE = "내 능력치"
DMG_NAME = "피해"
DMG_PERCENT_NAME = "피해 배율"
BASIC_PREFIX = "<color=#FF6B6B>평타 피해 <b>"
BASIC_SUFFIX = "</b></color>"
BASIC_SEPARATOR = " / "
# Fractions of the screen for the panel's bottom center. The game's clamp treats this point as the
# panel's center, so a higher value can push the top of a tall panel off the screen.
POS_X, POS_Y = 0.12, 0.30

# sub rsp,78h: UWOP_ALLOC_SMALL with info 14 is (14 * 8) + 8 bytes.
UNWIND_ALLOC_78 = bytes.fromhex("01040100" "04E20000")


def build_basic_helper(va: int, image_base: int, table: int, s_prefix: int, s_suffix: int, s_sep: int) -> bytes:
    """rcx = character, returns the "평타 피해" row or null for a class that is not in the table.
    Goes through CharAbilities.GetModifiedDamage, so this is the game's own non-critical hit value.
    Stack: [20h] outgoing arg; [38h] CharAbilities; [40h] ability; [48h] table row; [50h] hit;
    [58h] text; [60h] int for ToString; [68h] previous value; [70h] temp."""
    b = v1.X64Builder(va)

    def rip(prefix: bytes, target: int) -> None:
        b.emit(prefix + v1.i32(target - (b.va + len(prefix) + 4)))

    def concat_call() -> None:
        b.emit(b"\x45\x33\xC9")  # xor r9d,r9d
        b.emit(b"\x48\xC7\x44\x24\x20\x00\x00\x00\x00")
        b.call_abs(v1.STRING_CONCAT_4_VA)

    b.emit(b"\x48\x83\xEC\x78")  # sub rsp,78h
    b.emit(b"\x48\x8B\x81" + v1.u32(ABILITIES))  # mov rax,[rcx+ABILITIES]
    b.emit(b"\x48\x85\xC0")
    b.je("none")
    b.emit(b"\x48\x89\x44\x24\x38")
    b.emit(b"\x48\x8B\x80" + v1.u32(CHAR_ABILITIES_LIST))  # mov rax,[rax+B0h]
    b.emit(b"\x48\x85\xC0")
    b.je("none")
    b.emit(b"\x83\x78\x18\x00")  # cmp dword ptr [rax+18h],0 (array length)
    b.je("none")
    b.emit(b"\x48\x8B\x40\x20")  # mov rax,[rax+20h] (slot 0)
    b.emit(b"\x48\x85\xC0")
    b.je("none")
    b.emit(b"\x48\x89\x44\x24\x40")
    b.emit(b"\x48\x8B\x00")  # mov rax,[rax] (class)
    b.emit(b"\x48\x85\xC0")
    b.je("none")
    b.emit(b"\x4C\x8B\x90" + v1.u32(KLASS_GET_TOOLTIP_DESCRIPTION))  # mov r10,[rax+3B8h]
    rip(b"\x4C\x8D\x1D", image_base)  # lea r11,[image base]
    b.emit(b"\x4D\x29\xDA")  # sub r10,r11
    rip(b"\x4C\x8D\x1D", table)  # lea r11,[table]
    b.emit(b"\xB9" + v1.u32(len(BASIC_ATTACKS)))  # mov ecx,count

    b.mark("find")
    b.emit(b"\x45\x3B\x13")  # cmp r10d,[r11]
    b.je("found")
    b.emit(b"\x49\x83\xC3\x10")  # add r11,10h
    b.emit(b"\xFF\xC9")  # dec ecx
    b.jne("find")
    b.jmp("none")

    b.mark("found")
    b.emit(b"\x4C\x89\x5C\x24\x48")  # mov [rsp+48h],r11
    b.emit(b"\x33\xC0")
    b.emit(b"\x48\x89\x44\x24\x50")  # hit = 0
    b.emit(b"\x48\x89\x44\x24\x58")  # text = null
    b.emit(b"\xC7\x44\x24\x68" + v1.u32(0x80000000))  # previous = int.MinValue

    b.mark("hit")
    b.emit(b"\x8B\x44\x24\x50")  # mov eax,[rsp+50h]
    b.emit(b"\x83\xF8" + bytes((BASIC_HIT_SLOTS,)))
    b.jcc(0x8D, "finish")  # jge
    b.emit(b"\x48\x8B\x54\x24\x48")  # mov rdx,[rsp+48h]
    b.emit(b"\x0F\xB7\x4C\x82\x04")  # movzx ecx,word ptr [rdx+rax*4+4] (damage field)
    b.emit(b"\x85\xC9")
    b.je("finish")
    b.emit(b"\x0F\xB7\x44\x82\x06")  # movzx eax,word ptr [rdx+rax*4+6] (scaling field)
    b.emit(b"\x4C\x8B\x54\x24\x40")  # mov r10,[rsp+40h]
    b.emit(b"\x41\x8B\x14\x0A")  # mov edx,[r10+rcx]
    b.emit(b"\xF3\x41\x0F\x10\x14\x02")  # movss xmm2,[r10+rax]
    b.emit(b"\x48\x8B\x4C\x24\x38")  # mov rcx,[rsp+38h]
    b.emit(b"\x45\x33\xC9")  # isCrit = false
    b.emit(b"\x48\xC7\x44\x24\x20\x00\x00\x00\x00")
    b.call_abs(GET_MODIFIED_DAMAGE_VA)
    b.emit(b"\x3B\x44\x24\x68")  # cmp eax,[rsp+68h]
    b.je("next")  # a repeated value says nothing new
    b.emit(b"\x89\x44\x24\x68")
    b.emit(b"\x89\x44\x24\x60")
    b.emit(b"\x48\x8D\x4C\x24\x60")  # lea rcx,[rsp+60h] (Int32.ToString takes int*)
    b.emit(b"\x33\xD2")
    b.call_abs(INT32_TO_STRING_VA)
    b.emit(b"\x48\x8B\x4C\x24\x58")  # mov rcx,[rsp+58h]
    b.emit(b"\x48\x85\xC9")
    b.jne("join")
    b.emit(b"\x48\x89\x44\x24\x58")
    b.jmp("next")
    b.mark("join")
    b.emit(b"\x48\x89\x44\x24\x70")  # mov [rsp+70h],rax
    rip(b"\x48\x8D\x0D", s_sep)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x8B\xD0")  # mov rdx,rax
    b.emit(b"\x48\x8B\x4C\x24\x58")
    b.emit(b"\x4C\x8B\x44\x24\x70")  # mov r8,[rsp+70h]
    concat_call()
    b.emit(b"\x48\x89\x44\x24\x58")
    b.mark("next")
    b.emit(b"\xFF\x44\x24\x50")  # inc dword ptr [rsp+50h]
    b.jmp("hit")

    b.mark("finish")
    b.emit(b"\x48\x83\x7C\x24\x58\x00")  # cmp qword ptr [rsp+58h],0
    b.je("none")
    rip(b"\x48\x8D\x0D", s_prefix)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x89\x44\x24\x70")
    rip(b"\x48\x8D\x0D", s_suffix)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x4C\x8B\xC0")  # mov r8,rax
    b.emit(b"\x48\x8B\x4C\x24\x70")  # mov rcx,[rsp+70h]
    b.emit(b"\x48\x8B\x54\x24\x58")  # mov rdx,[rsp+58h]
    concat_call()
    b.jmp("return")

    b.mark("none")
    b.emit(b"\x33\xC0")
    b.mark("return")
    b.emit(b"\x48\x83\xC4\x78")
    b.emit(b"\xC3")
    return b.finish()


def build_helper(va: int, table: int, s_title: int, s_nl: int, color: int, fx: int, fy: int, basic_va: int, s_dmg: int, s_dmg_percent: int) -> bytes:
    """Stack: [20h][28h][30h] outgoing args; [38h] UIManager; [40h] character; [48h] text;
    [50h] index; [58h] temp; [60h] Vector3 position; [70h] temp."""
    b = v1.X64Builder(va)

    def load_ui_manager(fail: str) -> None:
        b.mov_rax_rip_qword(v1.UI_MANAGER_TYPE_PTR_SLOT_VA)
        b.emit(b"\x48\x85\xC0")
        b.je(fail)
        b.emit(b"\x48\x8B\x80\xB8\x00\x00\x00")  # mov rax,[rax+B8h]
        b.emit(b"\x48\x85\xC0")
        b.je(fail)
        b.emit(b"\x48\x8B\x40\x08")  # mov rax,[rax+8] (UIManager.Instance)
        b.emit(b"\x48\x85\xC0")
        b.je(fail)

    def rip(prefix: bytes, target: int) -> None:
        b.emit(prefix + v1.i32(target - (b.va + len(prefix) + 4)))

    b.emit(b"\x48\x83\xEC\x78")  # sub rsp,78h
    b.emit(b"\xB9" + v1.u32(KEY_X) + b"\x33\xD2")  # mov ecx,key; xor edx,edx
    b.call_abs(INPUT_GET_KEY_VA)
    b.emit(b"\x84\xC0")
    b.jne("held")

    # Not held: hide only on the frame the key was released, so other tooltips are left alone.
    b.emit(b"\xB9" + v1.u32(KEY_X) + b"\x33\xD2")
    b.call_abs(INPUT_GET_KEY_UP_VA)
    b.emit(b"\x84\xC0")
    b.je("done")
    load_ui_manager("done")
    b.emit(b"\x48\x8B\x48" + bytes((UI_MANAGER_TOOLTIP,)))  # mov rcx,[rax+70h]
    b.emit(b"\x48\x85\xC9")
    b.je("done")
    b.emit(b"\x33\xD2")
    b.call_abs(TOOLTIP_HIDE_VA)
    b.jmp("done")

    b.mark("held")
    b.emit(b"\xB9" + v1.u32(KEY_X) + b"\x33\xD2")
    b.call_abs(INPUT_GET_KEY_DOWN_VA)
    b.emit(b"\x84\xC0")
    b.jne("refresh")
    b.emit(b"\x33\xC9")
    b.call_abs(TIME_FRAME_COUNT_VA)
    b.emit(b"\xA9" + v1.u32(REFRESH_FRAME_MASK))  # test eax,mask
    b.jne("done")

    b.mark("refresh")
    load_ui_manager("done")
    b.emit(b"\x48\x89\x44\x24\x38")  # mov [rsp+38h],rax
    b.emit(b"\x48\x8B\x48" + bytes((UI_MANAGER_CHAT,)))  # mov rcx,[rax+30h]
    b.emit(b"\x48\x85\xC9")
    b.je("no_chat")
    b.emit(b"\x80\xB9" + v1.u32(UI_CHAT_IS_FOCUSED) + b"\x00")  # cmp byte ptr [rcx+E8h],0
    b.jne("done")  # typing in chat
    b.mark("no_chat")
    b.emit(b"\x33\xC9\x33\xD2\x45\x33\xC0")
    b.call_abs(v1.PLAYER_MANAGER_GET_CURRENT_AUTH_VIEW_CHARACTER_VA)
    b.emit(b"\x48\x85\xC0")
    b.je("done")  # no character, for example in the lobby
    b.emit(b"\x48\x89\x44\x24\x40")  # mov [rsp+40h],rax
    b.emit(b"\x33\xC0")
    b.emit(b"\x48\x89\x44\x24\x48")  # text = null
    b.emit(b"\x48\x89\x44\x24\x50")  # index = 0

    b.mark("loop")
    b.emit(b"\x8B\x44\x24\x50")  # mov eax,[rsp+50h]
    b.emit(b"\x83\xF8" + bytes((len(STATS),)))
    b.jcc(0x8D, "show")  # jge
    b.emit(b"\xC1\xE0\x04")  # shl eax,4
    rip(b"\x48\x8D\x15", table)  # lea rdx,[table]
    b.emit(b"\x48\x01\xC2")  # add rdx,rax
    b.emit(b"\x48\x8B\x4C\x24\x40")  # mov rcx,[rsp+40h]
    b.emit(b"\x80\x7A\x06" + bytes((BASIC_ATTACK_ROW,)))  # cmp byte ptr [rdx+6],row
    b.je("basic_row")
    b.emit(b"\x8B\x02")  # mov eax,[rdx]
    b.emit(b"\x48\x8B\x0C\x01")  # mov rcx,[rcx+rax] (component)
    b.emit(b"\x48\x85\xC9")
    b.je("next")
    b.emit(b"\x0F\xB7\x42\x04")  # movzx eax,word ptr [rdx+4]
    b.emit(b"\x80\x7A\x07\x00")  # cmp byte ptr [rdx+7],0
    b.jne("is_int")
    b.emit(b"\xF3\x0F\x10\x0C\x01")  # movss xmm1,[rcx+rax]
    b.jmp("scale")
    b.mark("is_int")
    b.emit(b"\xF3\x0F\x2A\x0C\x01")  # cvtsi2ss xmm1,dword ptr [rcx+rax]
    b.mark("scale")
    b.emit(b"\xF3\x0F\x59\x4A\x08")  # mulss xmm1,[rdx+8]
    b.emit(b"\xF3\x0F\x58\x4A\x0C")  # addss xmm1,[rdx+0Ch]
    b.emit(b"\x0F\xB6\x4A\x06")  # movzx ecx,byte ptr [rdx+6]
    b.emit(b"\x45\x33\xC0")
    b.call_abs(BUILD_ITEM_STAT_STR_VA)
    b.emit(b"\x48\x85\xC0")
    b.je("next")

    # The game calls both damage stats "피해". Rename only this panel's row.
    b.emit(b"\x83\x7C\x24\x50" + bytes((DMG_PERCENT_ROW_INDEX,)))  # cmp dword ptr [rsp+50h],index
    b.jne("append")
    b.emit(b"\x48\x89\x44\x24\x58")  # mov [rsp+58h],rax
    rip(b"\x48\x8D\x0D", s_dmg)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x89\x44\x24\x70")  # mov [rsp+70h],rax
    rip(b"\x48\x8D\x0D", s_dmg_percent)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x4C\x8B\xC0")  # mov r8,rax
    b.emit(b"\x48\x8B\x54\x24\x70")  # mov rdx,[rsp+70h]
    b.emit(b"\x48\x8B\x4C\x24\x58")  # mov rcx,[rsp+58h]
    b.emit(b"\x45\x33\xC9")
    b.call_abs(STRING_REPLACE_VA)

    b.mark("append")
    b.emit(b"\x48\x85\xC0")
    b.je("next")
    b.emit(b"\x48\x8B\x4C\x24\x48")  # mov rcx,[rsp+48h]
    b.emit(b"\x48\x85\xC9")
    b.jne("join")
    b.emit(b"\x48\x89\x44\x24\x48")
    b.jmp("next")
    b.mark("join")
    b.emit(b"\x48\x89\x44\x24\x58")  # mov [rsp+58h],rax
    rip(b"\x48\x8D\x0D", s_nl)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x8B\xD0")  # mov rdx,rax
    b.emit(b"\x48\x8B\x4C\x24\x48")  # mov rcx,[rsp+48h]
    b.emit(b"\x4C\x8B\x44\x24\x58")  # mov r8,[rsp+58h]
    b.emit(b"\x45\x33\xC9")
    b.emit(b"\x48\xC7\x44\x24\x20\x00\x00\x00\x00")
    b.call_abs(v1.STRING_CONCAT_4_VA)
    b.emit(b"\x48\x89\x44\x24\x48")
    b.mark("next")
    b.emit(b"\xFF\x44\x24\x50")  # inc dword ptr [rsp+50h]
    b.jmp("loop")

    b.mark("basic_row")
    b.call_abs(basic_va)  # rcx is still the character
    b.jmp("append")

    b.mark("show")
    b.emit(b"\x48\x83\x7C\x24\x48\x00")  # cmp qword ptr [rsp+48h],0
    b.je("done")
    rip(b"\x48\x8D\x0D", s_title)
    b.call_abs(v1.IL2CPP_STRING_NEW_VA)
    b.emit(b"\x48\x89\x44\x24\x58")
    b.emit(b"\x33\xC9")
    b.call_abs(SCREEN_WIDTH_VA)
    b.emit(b"\xF3\x0F\x2A\xC0")  # cvtsi2ss xmm0,eax
    rip(b"\xF3\x0F\x59\x05", fx)  # mulss xmm0,[fx]
    b.emit(b"\xF3\x0F\x11\x44\x24\x60")
    b.emit(b"\x33\xC9")
    b.call_abs(SCREEN_HEIGHT_VA)
    b.emit(b"\xF3\x0F\x2A\xC0")
    rip(b"\xF3\x0F\x59\x05", fy)
    b.emit(b"\xF3\x0F\x11\x44\x24\x64")
    b.emit(b"\x33\xC0\x89\x44\x24\x68")  # z = 0
    b.emit(b"\x48\x8B\x44\x24\x38")
    b.emit(b"\x48\x8B\x48" + bytes((UI_MANAGER_TOOLTIP,)))
    b.emit(b"\x48\x85\xC9")
    b.je("done")
    rip(b"\x48\x8D\x15", color)
    b.emit(b"\x4C\x8B\x44\x24\x58")  # r8 = title
    b.emit(b"\x4C\x8B\x4C\x24\x48")  # r9 = text
    b.emit(b"\x48\x8D\x44\x24\x60\x48\x89\x44\x24\x20")  # [rsp+20h] = &position
    b.emit(b"\x48\xC7\x44\x24\x28\x00\x00\x00\x00")  # fadeIn = false
    b.emit(b"\x48\xC7\x44\x24\x30\x00\x00\x00\x00")  # MethodInfo = null
    b.call_abs(TOOLTIP_SHOW_VA)

    # A tooltip that faded out earlier stays at alpha 0 when fadeIn is false. fadeIn = true would
    # restart the fade from 0 on every refresh, so make it fully visible here instead.
    b.emit(b"\x48\x8B\x44\x24\x38")
    b.emit(b"\x48\x8B\x48" + bytes((UI_MANAGER_TOOLTIP,)))
    b.emit(b"\x48\x85\xC9")
    b.je("done")
    b.emit(b"\x48\x8B\x49" + bytes((UI_TOOLTIP_ELEMENT,)))  # mov rcx,[rcx+48h]
    b.emit(b"\x48\x85\xC9")
    b.je("done")
    b.emit(b"\x48\x8B\x89" + v1.u32(UI_TOOLTIP_ELEMENT_FADE))  # mov rcx,[rcx+80h]
    b.emit(b"\x48\x85\xC9")
    b.je("done")
    b.emit(b"\x33\xD2")
    b.call_abs(FADE_IN_INSTANT_VA)

    b.mark("done")
    b.emit(b"\x33\xC9")  # the original call passes rcx = 0
    b.emit(b"\x48\x83\xC4\x78")
    b.jmp_abs(SCREEN_WIDTH_VA)
    return b.finish()


def build(data: bytes) -> bytes:
    if hashlib.sha256(data).hexdigest().upper() != BASE_SHA256:
        raise SystemExit("GameAssembly.dll is not the Korean patch v2 build")
    pe = pefile.PE(data=data, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == v1.PATCH_SECTION_NAME)
    if sec.PointerToRawData + sec.SizeOfRawData != len(data):
        raise SystemExit(".bapko is not the last raw data in the file")

    extra = bytearray(b"\0" * ((-sec.Misc_VirtualSize) % 16))
    cursor = lambda: sec.Misc_VirtualSize + len(extra)
    sec_va = base + sec.VirtualAddress

    def put(blob: bytes, align: int = 4) -> int:
        extra.extend(b"\0" * ((-cursor()) % align))
        off = cursor()
        extra.extend(blob)
        return sec_va + off

    table = put(b"".join(struct.pack("<IHBBff", comp, field, stat, 1 if is_int else 0, a, b_) for stat, comp, field, is_int, a, b_ in STATS), 16)
    color = put(struct.pack("<ffff", 1.0, 1.0, 1.0, 1.0))
    fx = put(struct.pack("<f", POS_X))
    fy = put(struct.pack("<f", POS_Y))
    s_title = put(TITLE.encode("utf-8") + b"\0", 1)
    s_nl = put(b"\n\0", 1)
    s_dmg = put(DMG_NAME.encode("utf-8") + b"\0", 1)
    s_dmg_percent = put(DMG_PERCENT_NAME.encode("utf-8") + b"\0", 1)
    s_prefix = put(BASIC_PREFIX.encode("utf-8") + b"\0", 1)
    s_suffix = put(BASIC_SUFFIX.encode("utf-8") + b"\0", 1)
    s_sep = put(BASIC_SEPARATOR.encode("utf-8") + b"\0", 1)

    def basic_row(fn_va: int, hits: tuple) -> bytes:
        cells = [v for hit in hits for v in hit] + [0] * (BASIC_HIT_SLOTS * 2 - 2 * len(hits))
        return struct.pack("<I6H", fn_va - base, *cells)

    basic_table = put(b"".join(basic_row(fn, hits) for fn, hits in BASIC_ATTACKS), 4)
    unwind_va = put(UNWIND_ALLOC_78, 4)
    extra.extend(b"\x90" * ((-cursor()) % 16))
    basic_va = sec_va + cursor()
    basic_code = build_basic_helper(basic_va, base, basic_table, s_prefix, s_suffix, s_sep)
    extra.extend(basic_code)
    extra.extend(b"\x90" * ((-cursor()) % 16))
    helper_off = cursor()
    helper_va = sec_va + helper_off
    code = build_helper(helper_va, table, s_title, s_nl, color, fx, fy, basic_va, s_dmg, s_dmg_percent)
    extra.extend(code)

    new_vsize = cursor()
    new_raw = v1.align_up(new_vsize, pe.OPTIONAL_HEADER.FileAlignment)
    if v1.align_up(sec.VirtualAddress + new_vsize, pe.OPTIONAL_HEADER.SectionAlignment) != pe.OPTIONAL_HEADER.SizeOfImage:
        raise SystemExit("section growth would change SizeOfImage")

    out = bytearray(data[: sec.PointerToRawData])
    out += data[sec.PointerToRawData : sec.PointerToRawData + sec.Misc_VirtualSize]
    out += extra
    out += b"\0" * (sec.PointerToRawData + new_raw - len(out))

    # Exception table. The v2 helpers share one unwind record and sit next to each other, so one
    # entry can cover all of them, which frees room for the new helper.
    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    pdata = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata")
    start = pdata.PointerToRawData + exc.Size - 12 * V2_HELPER_COUNT
    rows = [struct.unpack_from("<III", data, start + 12 * i) for i in range(V2_HELPER_COUNT)]
    if len({r[2] for r in rows}) != 1:
        raise SystemExit("v2 helpers do not share one unwind record")
    new_rows = (
        struct.pack("<III", rows[0][0], rows[-1][1], rows[0][2])
        + struct.pack("<III", basic_va - base, basic_va - base + len(basic_code), unwind_va - base)
        + struct.pack("<III", helper_va - base, helper_va - base + len(code), unwind_va - base)
    )
    old_len = 12 * V2_HELPER_COUNT
    out[start : start + old_len] = new_rows + b"\0" * (old_len - len(new_rows))
    new_exc = exc.Size - old_len + len(new_rows)
    struct.pack_into("<I", out, exc.get_field_absolute_offset("Size"), new_exc)
    struct.pack_into("<I", out, pdata.get_file_offset() + 8, pdata.Misc_VirtualSize - old_len + len(new_rows))

    # Section header and code size.
    hdr = sec.get_file_offset()
    struct.pack_into("<I", out, hdr + 8, new_vsize)
    struct.pack_into("<I", out, hdr + 16, new_raw)
    off = pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfCode")
    struct.pack_into("<I", out, off, pe.OPTIONAL_HEADER.SizeOfCode + new_raw - sec.SizeOfRawData)

    # Hook.
    hook_off = pe.get_offset_from_rva(HOOK_CALL_VA - base)
    expected = v1.rel32_bytes(0xE8, HOOK_CALL_VA, SCREEN_WIDTH_VA)
    if bytes(out[hook_off : hook_off + 5]) != expected:
        raise SystemExit("hook guard failed")
    out[hook_off : hook_off + 5] = v1.rel32_bytes(0xE8, HOOK_CALL_VA, helper_va)

    # Offline validation.
    result = bytes(out)
    pe2 = pefile.PE(data=result, fast_load=True)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    insns = list(md.disasm(code, helper_va))
    if sum(i.size for i in insns) != len(code) or insns[-1].mnemonic != "jmp":
        raise SystemExit("helper does not decode cleanly")
    basic_insns = list(md.disasm(basic_code, basic_va))
    if sum(i.size for i in basic_insns) != len(basic_code) or basic_insns[-1].mnemonic != "ret":
        raise SystemExit("basic attack helper does not decode cleanly")
    exc2 = pe2.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    pd2 = next(s for s in pe2.sections if s.Name.rstrip(b"\0") == b".pdata")
    last = [struct.unpack_from("<III", result, pd2.PointerToRawData + exc2.Size - 12 * k) for k in range(8, 0, -1)]
    if any(last[i][0] >= last[i + 1][0] for i in range(7)):
        raise SystemExit("exception table is not sorted")
    if last[-1][1] > pe2.OPTIONAL_HEADER.SizeOfImage:
        raise SystemExit("helper outside the image")
    print(f"helpers {basic_va:#x} {len(basic_code)} bytes, {helper_va:#x} {len(code)} bytes, section {new_vsize}/{new_raw}, exception entries ok")
    return result


def write_edits(base: bytes, built: bytes, out: Path) -> None:
    """Same format as build_ga_full_edits.py, so install.ps1 applies it with the same guarded code."""
    spec = importlib.util.spec_from_file_location("build_ga_full_edits", _src / "build_ga_full_edits.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    common = built[: len(base)]
    edits = [
        {"name": f"range_{i}", "offset": s, "expected": base[s:e].hex().upper(), "replacement": common[s:e].hex().upper()}
        for i, (s, e) in enumerate(tool.diff_ranges(base, common))
    ]
    rebuilt = bytearray(base)
    for e in edits:
        new = bytes.fromhex(e["replacement"])
        rebuilt[e["offset"] : e["offset"] + len(new)] = new
    rebuilt.extend(built[len(base) :])
    if bytes(rebuilt) != built:
        raise SystemExit("edit list does not reproduce the stat panel build")
    doc = {
        "schema_version": 1,
        "input_sha256": hashlib.sha256(base).hexdigest().upper(),
        "output_sha256": hashlib.sha256(built).hexdigest().upper(),
        "edits": edits,
        "append": built[len(base) :].hex().upper(),
    }
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("wrote", out, "edits", len(edits), "append bytes", len(built) - len(base))


def backup_path(game: Path) -> Path:
    return game / ".bapko-backup" / "v2" / "GameAssembly.dll.v2"


def game_running() -> bool:
    import subprocess

    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq bapbap.exe", "/NH"], capture_output=True, text=True, errors="replace").stdout
    return "bapbap.exe" in out.lower()


def replace(path: Path, blob: bytes) -> None:
    tmp = path.with_name(path.name + ".bapko-new")
    tmp.write_bytes(blob)
    if tmp.read_bytes() != blob:
        raise SystemExit("write verification failed")
    os.replace(tmp, path)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game-dir", type=Path, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true")
    g.add_argument("--remove", action="store_true")
    g.add_argument("--check", action="store_true", help="build in memory without touching the game")
    g.add_argument("--write-edits", type=Path, metavar="JSON", help="write the v2 -> stat panel edit list for install.ps1")
    a = p.parse_args()
    dll = a.game_dir / "GameAssembly.dll"
    bak = backup_path(a.game_dir)
    data = dll.read_bytes()
    is_base = hashlib.sha256(data).hexdigest().upper() == BASE_SHA256
    if a.check or a.write_edits:
        base = data if is_base else bak.read_bytes()
        built = build(base)
        print("output", hashlib.sha256(built).hexdigest().upper(), "current is base:", is_base)
        if a.write_edits:
            write_edits(base, built, a.write_edits)
        return 0
    if game_running():
        raise SystemExit("Close BAPBAP first.")
    if a.remove:
        if is_base:
            print("Mod is not installed.")
            return 0
        blob = bak.read_bytes()
        if hashlib.sha256(blob).hexdigest().upper() != BASE_SHA256:
            raise SystemExit("backup does not match the v2 build")
        replace(dll, blob)
        print("Removed. GameAssembly.dll is back to v2.")
        return 0
    if not is_base:
        built = build(bak.read_bytes())
        if built == data:
            print("Mod is already installed.")
            return 0
        raise SystemExit("GameAssembly.dll is not v2. Run --remove first.")
    built = build(data)
    bak.parent.mkdir(parents=True, exist_ok=True)
    if not bak.exists() or hashlib.sha256(bak.read_bytes()).hexdigest().upper() != BASE_SHA256:
        replace(bak, data)
    replace(dll, built)
    if dll.read_bytes() != built:
        raise SystemExit("install verification failed")
    print("Installed. Hold X in a match. sha256", hashlib.sha256(built).hexdigest().upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
