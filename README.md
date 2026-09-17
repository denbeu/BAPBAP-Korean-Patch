# BAPBAP 비공식 한국어 패치

**English: [README_EN.md](README_EN.md)**

Steam용 **BAPBAP build 19658140**에서 검증된 비공식 한국어 패치입니다.

이 저장소의 목적은 두 가지입니다.

1. 일반 사용자가 출시된 Steam 버전에 한국어 패치를 설치하고 제거할 수 있게 합니다.
2. 패처가 무엇을 하는지 검토하고 직접 빌드할 수 있도록 자체 작성 source code를 함께 공개합니다.

Maison Bap의 공식 소스 프로젝트에 Korean locale을 통합하기 위한 개발자 전달 자료는 별도 저장소로 분리합니다. 이 저장소는 **released Steam binary patch distribution**을 위한 저장소입니다.

## 게임 파일은 포함하지 않습니다

이 저장소에는 `GameAssembly.dll`, `sharedassets0.assets`, `level0`, 원본/수정 Unity asset, Steam 원본 binary, backup, `Player.log`가 포함되지 않습니다.

설치기는 사용자가 보유한 Steam BAPBAP 파일을 로컬에서 읽고, 지원하는 원본 SHA-256과 일치할 때만 임시 폴더에서 패치 결과를 생성합니다. 최종 결과 해시까지 검증된 경우에만 게임 파일을 교체합니다.

`tools/`의 EXE는 BAPBAP 게임 파일이 아니라 이 프로젝트에서 작성한 패처/도구의 사전 빌드본입니다. 동일한 자체 작성 source는 `source/`에 포함되어 있습니다.

## 지원 범위

- Steam App ID: `2226280`
- 지원 Steam build ID: `19658140`
- phrase rows: `1690`
- 한국어 번역/용어/문맥 QA 완료
- TMP 한글 fallback/font fix 포함
- TRAINING 및 확인된 literal UI patch 포함
- dynamic UI, 게임플레이 툴팁 조각, 실시간 언어 갱신을 위한 제한적인 한국어 전용 `GameAssembly.dll` patch 포함

세 원본/최종 SHA-256은 [PATCH_SCOPE.md](PATCH_SCOPE.md)에 고정되어 있습니다. 지원하지 않는 build, 다른 모드가 적용된 파일, 수동 수정 파일에는 패치를 적용하지 않습니다.

## 패치가 수정하는 파일

설치 시 사용자의 로컬 게임 설치본에서 다음 세 파일을 대상으로 새 결과물을 생성합니다.

- `bapbap_Data/sharedassets0.assets`
  - 기존 Turkish locale phrase slot에 1,690행 한국어 phrase를 적용
  - 확인된 TRAINING/literal UI 및 캐릭터 표시 문자열 보정
  - 기존 Noto Sans CJK TMP FontAsset을 이용한 한글 fallback 및 multi-atlas 설정 보정
- `bapbap_Data/level0`
  - 확인된 training UI literal/localization-key routing 보정
- `GameAssembly.dll`
  - phrase table 밖에서 런타임에 생성되는 일부 UI/툴팁만 대상으로 하는 제한적 한국어 전용 patch
  - 현재 범위는 lobby-name formatting, boolean 표시, ordinal/rank formatting, 한국어 툴팁 복합 조각, 소피아 Q 시간 표기, 언어 변경 시 같은 장면의 스킬명/열린 툴팁 갱신 경로입니다.

`GameAssembly.dll` patch가 있다는 사실을 숨기지 않습니다. 이 patch는 **지원 build의 정확한 원본 SHA-256 및 target-byte guard**를 통과해야만 생성되며, source는 `source/patch_gameassembly_dynamic_ui.py`에 있습니다.

현재 비공식 패치는 정식 Korean locale을 추가하는 대신 **Turkish locale 슬롯을 한국어용으로 재사용**합니다. 설치 후 게임 언어에서 Türkçe를 선택하면 한국어가 표시됩니다. 이것은 source project 접근 권한이 없는 community patch의 호환 방식입니다.

## 설치 전 요구 사항

1. Steam에서 BAPBAP이 지원 build로 설치되어 있어야 합니다.
2. BAPBAP을 완전히 종료합니다.
3. prebuilt `BapAssetTool.exe` 실행을 위해 Windows에 **.NET 8 Runtime**이 필요합니다.
4. 다른 모드나 수동 수정이 적용된 대상 파일은 지원하지 않습니다. 설치기는 원본 SHA-256이 다르면 중단합니다.

## 설치

일반 사용자는 repository에 포함된 prebuilt patcher를 사용하면 됩니다. 별도 source build는 필요하지 않습니다.

`install.bat`을 실행하세요. `install.bat`은 같은 폴더의 `install.ps1`을 PowerShell로 실행하는 간단한 wrapper이며, Steam 설치 위치를 자동 탐색합니다.

자동 탐색이 실패하면 PowerShell에서 직접 경로를 지정할 수 있습니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP"
```

게임 파일을 변경하지 않고 전체 patch chain이 검증된 최종 해시를 재현하는지만 확인하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP" -DryRun
```

설치기는 원본 3파일의 해시를 확인하고 임시 폴더에서 patch를 만든 뒤, 세 결과가 모두 [PATCH_SCOPE.md](PATCH_SCOPE.md)의 최종 해시와 정확히 일치할 때만 교체합니다.

## 백업과 제거

최초 설치 시 검증된 원본 3파일은 게임 폴더의 다음 위치에 보관됩니다.

```text
.bapko-backup\build-19658140\
```

제거하려면 BAPBAP을 종료한 뒤 `uninstall.bat`을 실행하세요. 이 BAT 역시 `uninstall.ps1` wrapper입니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP"
```

제거기는 backup 원본 해시와 현재 대상 파일 상태를 확인한 뒤에만 복구합니다. 알 수 없는 수정 상태를 발견하면 덮어쓰지 않고 중단합니다.

## Steam 업데이트 후

게임 업데이트로 build 또는 대상 파일 해시가 변경되면 설치기는 패치를 거부합니다. 예전 게임 binary를 새 build에 강제로 덮어쓰지 마세요. 새 build가 검증될 때까지 기다려야 합니다.

## 백신/SmartScreen 경고

`tools/GameAssemblyPatcher.exe`는 Python/PyInstaller로 만든 one-file executable이며, 프로그램의 목적 자체가 사용자의 로컬 게임 binary를 검증 후 수정하는 것입니다. 이런 특성 때문에 일부 보안 제품에서 휴리스틱 경고나 오탐이 발생할 수 있습니다.

경고가 발생했다면 보안 기능을 무작정 끄지 말고, `source/`를 검토하거나 아래 절차로 직접 빌드해 사용하세요.

## Source code

일반 사용자는 `tools/`의 prebuilt patcher만 사용하면 됩니다. `source/`는 **투명성, 감사, 직접 빌드 및 재현 검증**을 위해 포함합니다.

```text
source/
  BapAssetTool.csproj
  BapAssetTool.Program.cs
  packages.lock.json
  patch_gameassembly_dynamic_ui.py
  requirements-source.txt
```

배포 source는 현재 프로젝트의 검증된 patch logic과 byte-for-byte 동일하게 복사되어 있습니다.

## Building from source

다음은 이번 배포 준비 과정에서 실제로 검증한 Windows toolchain입니다.

- .NET SDK: `8.0.416` (`net8.0` target)
- Python: `3.14.5`
- PyInstaller: `6.22.3`
- `pefile`: `2024.8.26`
- `capstone`: `5.0.9`

현재 prebuilt Python tool은 Python 3.14.5 환경에서 검증했습니다. source는 Python 3.10+ 문법을 사용하지만, 다른 Python 버전에서의 EXE 재현은 이번 release QA 범위에 포함하지 않았습니다.

### BapAssetTool

`packages.lock.json`은 직접 사용하는 NuGet dependency(`AssetsTools.NET 3.0.5`)의 버전과 content hash를 기록하기 위해 포함합니다. 현재 SDK의 `win-x64` publish 단계는 runtime-specific restore를 추가로 수행할 수 있으므로, 이 파일만으로 최종 EXE byte hash까지 고정된다고 보지는 않습니다.

Repository root에서:

```powershell
dotnet restore source\BapAssetTool.csproj
dotnet publish source\BapAssetTool.csproj -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true -o build\BapAssetTool
```

결과 EXE:

```text
build\BapAssetTool\BapAssetTool.exe
```

현재 `tools/BapAssetTool/BapAssetTool.exe`도 같은 C# source에서 생성한 framework-dependent single-file tool입니다.

### GameAssembly patcher

먼저 Python dependency를 설치합니다.

```powershell
python -m pip install -r source\requirements-source.txt
```

Source script의 CLI 확인:

```powershell
python source\patch_gameassembly_dynamic_ui.py --help
```

지원되는 본인 소유 `GameAssembly.dll`을 대상으로 source script를 직접 실행하는 형식은 다음과 같습니다.

```powershell
python source\patch_gameassembly_dynamic_ui.py --input "D:\SteamLibrary\steamapps\common\BAPBAP\GameAssembly.dll" --output build\GameAssembly.dll --report build\GameAssembly.patch-report.json
```

현재 `tools/GameAssemblyPatcher.exe`와 같은 one-file 형태를 빌드한 검증 명령은 다음과 같습니다.

```powershell
pyinstaller --onefile --name GameAssemblyPatcher --distpath build\GameAssemblyPatcher --workpath build\pyinstaller-work --specpath build\pyinstaller-spec source\patch_gameassembly_dynamic_ui.py
```

PyInstaller/.NET publish 결과물 자체의 SHA-256이 빌드 환경 metadata 때문에 항상 byte-for-byte 동일하다고 보장하지는 않습니다. 대신 이번 QA에서는 공개 source에서 다시 빌드한 두 도구를 사용해 `install.ps1 -DryRun` 전체 chain을 실행했고, 게임 patch 결과 3개의 검증된 최종 SHA-256이 동일하게 재현되는 것을 확인했습니다.

## Third-party components

Bundled dependency와 license 정보는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 및 `THIRD_PARTY_LICENSES/`를 참고하세요.

## License / rights

- 이 프로젝트가 직접 작성한 `BapAssetTool`, GameAssembly patcher, PowerShell/batch installer, 기타 자체 작성 script/config logic은 [`LICENSE`](LICENSE)의 **MIT License**로 배포합니다.
- 우리가 작성한 **한국어 번역 기여물**은 [`TRANSLATION_LICENSE.md`](TRANSLATION_LICENSE.md)에 따라 **CC BY 4.0**으로 제공합니다.
- 위 라이선스는 BAPBAP 원문, 게임 binary/source, Unity asset, 캐릭터, 상표, 로고, 기타 원저작물에 대한 권리를 부여하지 않습니다. 해당 권리는 Maison Bap 및 각 권리자에게 있습니다.
- 제3자 dependency에는 각자의 라이선스가 별도로 적용됩니다. 자세한 내용은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하세요.

한 파일에 code/config logic과 한국어 localization 문자열이 함께 들어 있는 경우에도 각각의 저작물 부분에 위 라이선스가 별도로 적용됩니다.

이 프로젝트는 Maison Bap의 공식 패치가 아닙니다.
