# Unofficial BAPBAP Korean Patch

**한국어: [README.md](README.md)**

This repository contains an unofficial Korean localization patch verified against **BAPBAP Steam build 19658140**.

It has two goals:

1. Let players install and remove the Korean patch on the released Steam game.
2. Publish the complete authored patcher source so the patch behavior can be audited and rebuilt independently.

The Maison Bap developer handoff for integrating Korean into the original source project is intentionally kept in a separate repository. This repository is for **released Steam binary patch distribution**.

## No game binaries are distributed

This repository does not contain `GameAssembly.dll`, `sharedassets0.assets`, `level0`, original or modified Unity assets, Steam-extracted binaries, backups, or Player logs.

The installer reads the user's own Steam installation locally. It only operates when the source files match the supported SHA-256 values, builds patched outputs in a temporary directory, and replaces game files only after the generated outputs match the verified final hashes.

The EXEs under `tools/` are prebuilt versions of patcher/tools authored by this project, not BAPBAP game files. Their corresponding authored source is included under `source/`.

## Supported scope

- Steam App ID: `2226280`
- Supported Steam build ID: `19658140`
- Phrase rows: `1690`
- Reviewed Korean translation, terminology, and context
- TMP Hangul fallback/font fix
- Verified TRAINING and literal-UI patches
- Limited Korean-only runtime `GameAssembly.dll` patch for dynamic UI, tooltip fragments, and live language refresh

The supported original and patched SHA-256 values are pinned in [PATCH_SCOPE.md](PATCH_SCOPE.md). Unsupported builds, manually modified files, and target files changed by other mods are rejected.

## Files modified by the patch

The installer generates replacements for five files from the user's local game installation. Patch v2 is layered on the verified v1 output, so a fresh install and an upgrade from v1 produce identical files.

- `bapbap_Data/sharedassets0.assets`
  - replaces the existing Turkish locale phrase slot with the 1,690-row Korean phrase payload;
  - applies verified TRAINING/literal UI and character-display string fixes, and translates `#` literal strings and static TMP default text;
  - configures Hangul fallback through the game's existing Noto Sans CJK TMP FontAsset and enables its multi-atlas setting.
- `bapbap_Data/level0`
  - applies verified training-UI literal/localization-key routing fixes, and translates `#` literal strings and static TMP default text.
- `bapbap_Data/resources.assets`
  - translates `#` literal strings and static TMP default text on placed map objects.
- `bapbap_Data/il2cpp_data/Metadata/global-metadata.dat`
  - points 66 UI string literals hard-coded in managed code at Korean text.
- `GameAssembly.dll`
  - applies a limited patch for text generated outside the normal phrase table;
  - the current scope covers lobby-name formatting, boolean labels, ordinal/rank formatting, Korean tooltip compound fragments, Sofia Q duration formatting, same-scene ability-title/tooltip refresh after language changes, stat-fragment word order, and keeping the friend list from removing nickname characters.

The `GameAssembly.dll` patch is intentionally disclosed. It is generated only after the exact supported source SHA-256 and target-byte guards pass. Its complete source is `source/patch_gameassembly_dynamic_ui.py` and `source/patch_gameassembly_v2.py`. See [PATCH_SCOPE.md](PATCH_SCOPE.md) for root causes and which changes apply to other locales.

Because the community patch has no access to the official source project, it currently reuses the **Turkish locale slot** for Korean instead of adding a native Korean locale. Select Türkçe in the in-game language setting after installation. This is a community-patch compatibility mechanism, not an official integration design.

## Requirements

1. Install the supported BAPBAP build through Steam.
2. Close BAPBAP before installing or uninstalling.
3. Install the **.NET 8 Runtime** for the prebuilt `BapAssetTool.exe`.
4. The target files must match the supported original or v1 hashes. Files modified by another mod or by hand are rejected.

## Install

### Easiest: patch tool

Download `BAPBAP-Korean-Patcher.exe` from the [releases page](https://github.com/denbeu/BAPBAP-Korean-Patch/releases/latest), close BAPBAP, run it, confirm the game folder, and press the install button. It is a window around `install.ps1` and `uninstall.ps1`, so the result is the same. The program is unsigned, so Windows SmartScreen may warn. It tells you if the .NET 8 Runtime is missing.

### With scripts

Normal users can use the prebuilt patchers under `tools/`; building from source is not required.

Run `install.bat`. It is a small wrapper that invokes `install.ps1` with PowerShell and forwards any arguments. The PowerShell installer attempts to locate the Steam installation automatically.

If auto-detection fails:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP"
```

To run the full patch chain and verify the generated final hashes without changing game files:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP" -DryRun
```

The installer validates the original or v1 files, builds replacements in a temporary directory, and installs them only when all five outputs exactly match [PATCH_SCOPE.md](PATCH_SCOPE.md).

## Backup and uninstall

The files present before installation are stored under:

```text
.bapko-backup\build-19658140\   Steam originals (fresh install), resources.assets, global-metadata.dat
.bapko-backup\v1\               v1 files (upgrade from v1)
```

Close BAPBAP and run `uninstall.bat`. Like the install BAT, it wraps `uninstall.ps1`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP"
```

The uninstaller validates both the backup hashes and the current target-file state before restoring anything. It restores the Steam originals when that backup exists, otherwise the v1 state; use Steam's "Verify integrity of game files" to get originals from there. Unknown modifications cause it to stop rather than overwrite them.

## Steam updates

If a BAPBAP update changes the build or target-file hashes, the installer refuses to patch. Do not force an older game binary onto a newer build. Wait until the new build has been reviewed and supported.

## Antivirus / SmartScreen notes

`tools/GameAssemblyPatcher.exe` is a Python/PyInstaller one-file executable and its intended function is to validate and modify a local game binary. Those characteristics can trigger heuristic antivirus or SmartScreen warnings on some systems.

If a warning appears, do not blindly disable security software. Review `source/` or build the tools yourself using the verified instructions below.

## Source code

Normal users only need the prebuilt tools. `source/` is provided for **transparency, auditing, independent builds, and reproducibility checks**.

```text
source/
  BapAssetTool.csproj
  BapAssetTool.Program.cs
  packages.lock.json
  patch_gameassembly_dynamic_ui.py
  requirements-source.txt
```

The distributed source is a byte-for-byte copy of the verified patch logic used by the current project state.

## Building from source

The following Windows toolchain was actually used and verified while preparing this package:

- .NET SDK: `8.0.416` (`net8.0` target)
- Python: `3.14.5`
- PyInstaller: `6.22.3`
- `pefile`: `2024.8.26`
- `capstone`: `5.0.9`

The current prebuilt Python tool was validated with Python 3.14.5. The source uses Python 3.10+ syntax, but rebuilding the EXE with other Python versions was outside this release QA scope.

### BapAssetTool

`packages.lock.json` records the version and content hash of the directly used NuGet dependency (`AssetsTools.NET 3.0.5`). The current SDK can perform an additional runtime-specific restore during `win-x64` publish, so this file is not presented as a guarantee of byte-identical final EXE hashes.

From the repository root:

```powershell
dotnet restore source\BapAssetTool.csproj
dotnet publish source\BapAssetTool.csproj -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true -o build\BapAssetTool
```

Output:

```text
build\BapAssetTool\BapAssetTool.exe
```

`tools/BapAssetTool/BapAssetTool.exe` is likewise a framework-dependent single-file executable built from the supplied C# source.

### GameAssembly patcher

Install the pinned Python dependencies:

```powershell
python -m pip install -r source\requirements-source.txt
```

Inspect the source CLI:

```powershell
python source\patch_gameassembly_dynamic_ui.py --help
```

To execute the source script directly against a supported `GameAssembly.dll` that you own:

```powershell
python source\patch_gameassembly_dynamic_ui.py --input "D:\SteamLibrary\steamapps\common\BAPBAP\GameAssembly.dll" --output build\GameAssembly.dll --report build\GameAssembly.patch-report.json
```

The verified one-file build command corresponding to `tools/GameAssemblyPatcher.exe` is:

```powershell
pyinstaller --onefile --name GameAssemblyPatcher --distpath build\GameAssemblyPatcher --workpath build\pyinstaller-work --specpath build\pyinstaller-spec source\patch_gameassembly_dynamic_ui.py
```

.NET/PyInstaller executable bytes are not claimed to be deterministically identical across build environments. Instead, release QA rebuilt both tools from the public source and ran the complete `install.ps1 -DryRun` chain with those rebuilt tools; all three generated game outputs reproduced the same verified final SHA-256 values.

## Third-party components

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `THIRD_PARTY_LICENSES/` for bundled dependency/license information.

## License / rights

- `BapAssetTool`, the GameAssembly patcher, PowerShell/batch installers, and other source/scripts/config logic authored by this project are distributed under the **MIT License** in [`LICENSE`](LICENSE).
- Korean translation contributions authored by this project are provided under **CC BY 4.0** as described in [`TRANSLATION_LICENSE.md`](TRANSLATION_LICENSE.md).
- These licenses do not grant rights in BAPBAP's original text, binaries/source, Unity assets, characters, trademarks, logos, or other original game content. Those rights remain with Maison Bap and the applicable rights holders.
- Third-party dependencies remain subject to their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Where a file contains both authored code/config logic and Korean localization strings, the applicable license follows the respective copyrighted contribution rather than automatically covering unrelated game material.

This project is not an official Maison Bap release.
