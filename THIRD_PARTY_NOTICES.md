# Third-party notices

This repository does not redistribute BAPBAP game binaries or extracted Unity assets.

The prebuilt patcher tools bundle or depend on the following third-party components:

| Component | Version | Used by | License | License text |
| --- | --- | --- | --- | --- |
| AssetsTools.NET | 3.0.5 | `BapAssetTool.exe` | MIT | `THIRD_PARTY_LICENSES/AssetsTools.NET.txt` |
| pefile | 2024.8.26 | `GameAssemblyPatcher.exe` | MIT | `THIRD_PARTY_LICENSES/pefile.txt` |
| Capstone | 5.0.9 | `GameAssemblyPatcher.exe` | BSD-style | `THIRD_PARTY_LICENSES/Capstone.txt` |
| PyInstaller | 6.22.3 | packaging `GameAssemblyPatcher.exe` | GPLv2-or-later with the PyInstaller bootloader exception | `THIRD_PARTY_LICENSES/PyInstaller.txt` |
| Python | 3.14.5 runtime used by the one-file build | `GameAssemblyPatcher.exe` | Python Software Foundation License | `THIRD_PARTY_LICENSES/Python.txt` |

`tools/GameAssemblyPatcher.exe` is a convenience one-file executable generated from `source/patch_gameassembly_dynamic_ui.py` with the versions listed above.

`tools/BapAssetTool/BapAssetTool.exe` is a framework-dependent .NET 8 single-file executable generated from the C# source in `source/`; its AssetsTools.NET dependency is bundled into that executable.

The third-party licenses listed here apply only to their respective components. They do not grant a license to BAPBAP game content and are separate from this repository's MIT-licensed authored source code and CC BY 4.0 Korean translation contributions.

Upstream project references:

- AssetsTools.NET: https://github.com/nesrak1/AssetsTools.NET
- pefile: https://github.com/erocarrera/pefile
- Capstone: https://www.capstone-engine.org
- PyInstaller: https://pyinstaller.org
- Python: https://www.python.org
