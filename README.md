# **개발 중인 버전입니다. 일부 특전/능력 설명에서 문장 조합 또는 효과 수치 표현이 부정확할 수 있습니다. 정식 릴리스 전까지 번역 QA를 계속 진행하고 있습니다.**

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

원본/최종 SHA-256은 [PATCH_SCOPE.md](PATCH_SCOPE.md)에 고정되어 있습니다. 지원하지 않는 build, 다른 모드가 적용된 파일, 수동 수정 파일에는 패치를 적용하지 않습니다.

## v2 변경 사항

- 킬로그, 팀원 이름, 점수판의 한글 닉네임이 □로 깨지던 문제 수정
- 친구 목록에서 한글 닉네임의 끝 글자가 사라지던 문제 수정
- 증강의 능력치 표기 어순 수정(`-150 ♥체력` → `♥체력 -150`)과 어색한 증강 설명 36건 수정
- 경기 중에는 로비 서버 연결 끊김 알림을 표시하지 않음(경기 연결과 별개인 알림)
- 미번역 문자열 번역: 소모품, 게임 모드, 상호작용, 핑, 꾸미기 아이템 이름 등 1,125종과 고정 UI 157종, 코드 내 문구 66종
- 기존 v1 설치본에서 그대로 업그레이드 가능

v2는 v1 위에 적용되는 증분 패치입니다. Steam 원본에서 설치하든 v1에서 업그레이드하든 결과 파일은 같습니다.

## 패치가 수정하는 파일

설치 시 사용자의 로컬 게임 설치본에서 다음 다섯 파일을 대상으로 새 결과물을 생성합니다.

- `bapbap_Data/sharedassets0.assets`
  - 기존 Turkish locale phrase slot에 1,690행 한국어 phrase를 적용
  - 확인된 TRAINING/literal UI, 캐릭터 표시 문자열, `#` 리터럴 문자열, 고정 TMP 기본 텍스트 번역
  - 기존 Noto Sans CJK TMP FontAsset을 이용한 한글 fallback 및 multi-atlas 설정 보정
- `bapbap_Data/level0`
  - 확인된 training UI literal/localization-key routing 보정, `#` 리터럴과 고정 TMP 기본 텍스트 번역
- `bapbap_Data/resources.assets`
  - 맵에 배치된 오브젝트의 `#` 리터럴과 고정 TMP 기본 텍스트 번역
- `bapbap_Data/il2cpp_data/Metadata/global-metadata.dat`
  - 코드에 하드코딩된 UI 문구 66종을 번역문으로 연결
- `GameAssembly.dll`
  - phrase table 밖에서 런타임에 생성되는 일부 UI/툴팁을 대상으로 하는 제한적 patch
  - 현재 범위는 lobby-name formatting, boolean 표시, ordinal/rank formatting, 한국어 툴팁 복합 조각, 소피아 Q 시간 표기, 언어 변경 시 같은 장면의 스킬명/열린 툴팁 갱신 경로, 능력치 조각 어순, 친구 목록 닉네임 글자 제거 방지입니다.

`GameAssembly.dll` patch가 있다는 사실을 숨기지 않습니다. 이 patch는 **지원 build의 정확한 원본 SHA-256 및 target-byte guard**를 통과해야만 생성되며, source는 `source/patch_gameassembly_dynamic_ui.py`에 있습니다.

현재 비공식 패치는 정식 Korean locale을 추가하는 대신 **Turkish locale 슬롯을 한국어용으로 재사용**합니다. 설치 후 게임 언어에서 Türkçe를 선택하면 한국어가 표시됩니다. 이것은 source project 접근 권한이 없는 community patch의 호환 방식입니다.

## 설치 전 요구 사항

1. Steam에서 BAPBAP이 지원 build로 설치되어 있어야 합니다.
2. BAPBAP을 완전히 종료합니다.
3. prebuilt `BapAssetTool.exe` 실행을 위해 Windows에 **.NET 8 Runtime**이 필요합니다.
4. 다른 모드나 수동 수정이 적용된 대상 파일은 지원하지 않습니다. 설치기는 원본 SHA-256이 다르면 중단합니다.

## 설치

### 가장 쉬운 방법: 패치 도구

1. [릴리즈 페이지](https://github.com/denbeu/BAPBAP-Korean-Patch/releases/latest)에서 `BAPBAP-Korean-Patcher.exe`를 받습니다.
2. BAPBAP을 종료한 뒤 실행합니다. 게임 폴더는 자동으로 찾습니다. 못 찾으면 `찾아보기`로 `bapbap.exe`가 있는 폴더를 지정하세요.
3. `한글 패치 설치`를 누르고 확인합니다. 몇 분 걸릴 수 있습니다.
4. 게임 설정에서 언어를 **Türkçe**로 선택합니다.

제거는 같은 도구의 `패치 제거` 버튼으로 할 수 있습니다. 이 도구는 아래 `install.ps1`, `uninstall.ps1`을 그대로 실행하는 창일 뿐이라 설치 결과는 같습니다.

서명되지 않은 프로그램이라 Windows SmartScreen 경고가 뜰 수 있습니다. **.NET 8 Runtime**이 없으면 도구가 안내합니다.

### 스크립트로 설치

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

설치기는 다섯 파일의 상태를 각각 확인하고 임시 폴더에서 patch를 만든 뒤, 결과가 [PATCH_SCOPE.md](PATCH_SCOPE.md)의 최종 해시와 정확히 일치할 때만 교체합니다. 교체 직전에 게임 드라이브에서 한 번 더 검증하고 이름 변경으로 교체하므로, 도중에 중단돼도 반쯤 쓴 파일이 남지 않습니다. 이전 실행이 중단되어 파일이 어긋나 있으면 검증된 백업을 사용해 이어서 설치합니다.

## 백업과 제거

설치 전 파일은 게임 폴더의 다음 위치에 보관됩니다.

```text
.bapko-backup\build-19658140\   Steam 원본(원본에서 설치한 경우), resources.assets, global-metadata.dat
.bapko-backup\v1\               v1에서 업그레이드한 경우의 v1 파일
```

제거하려면 BAPBAP을 종료한 뒤 `uninstall.bat`을 실행하세요. 이 BAT 역시 `uninstall.ps1` wrapper입니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -GameDir "D:\SteamLibrary\steamapps\common\BAPBAP"
```

제거기는 backup 해시와 현재 대상 파일 상태를 확인한 뒤에만 복구합니다. Steam 원본 backup이 있으면 원본으로, 없으면 v1 상태로 되돌립니다. v1 상태에서 Steam 원본이 필요하면 Steam의 "게임 파일 무결성 검사"를 사용하세요. 알 수 없는 수정 상태를 발견하면 덮어쓰지 않고 중단합니다.

## Steam 업데이트 후

게임 업데이트로 build 또는 대상 파일 해시가 변경되면 설치기는 패치를 거부합니다. 예전 게임 binary를 새 build에 강제로 덮어쓰지 마세요. 새 build가 검증될 때까지 기다려야 합니다.

## 백신/SmartScreen 경고

이 패치의 목적 자체가 사용자의 로컬 게임 binary를 검증 후 수정하는 것이라, 일부 보안 제품에서 휴리스틱 경고나 오탐이 발생할 수 있습니다. v2.0.1부터 설치 과정에서 Python 패처(`tools/GameAssemblyPatcher.exe`)를 실행하지 않습니다. `GameAssembly.dll`은 `install.ps1`이 byte guard를 확인하며 직접 수정합니다.

경고가 발생했다면 보안 기능을 무작정 끄지 말고, `source/`를 검토하거나 아래 절차로 직접 빌드해 사용하세요.

## Source code

일반 사용자는 `tools/`의 prebuilt patcher만 사용하면 됩니다. `source/`는 **투명성, 감사, 직접 빌드 및 재현 검증**을 위해 포함합니다.

```text
source/
  BapAssetTool.csproj
  BapAssetTool.Program.cs
  packages.lock.json
  patch_gameassembly_dynamic_ui.py
  patch_gameassembly_v2.py
  build_ga_full_edits.py
  build_v2_payload.py
  requirements-source.txt
  gui/BapKoreanPatcher.cs
  gui/build_gui.ps1
```

패치 도구 EXE는 Windows에 기본 포함된 C# 컴파일러로 빌드합니다: `powershell -NoProfile -ExecutionPolicy Bypass -File source\gui\build_gui.ps1`

`patch_gameassembly_v2.py`는 v1 결과물에 적용할 byte edit 목록(`payload/v2/gameassembly_edits.json`)을, `build_ga_full_edits.py`는 Steam 원본에서 최종 결과로 바로 가는 목록(`gameassembly_edits_from_original.json`)을 생성합니다. `install.ps1`이 byte guard를 확인하며 이를 적용하므로 설치에 Python은 필요하지 않습니다. `build_v2_payload.py`는 번역표에서 `payload/v2`를 다시 생성하는 개발자용 도구이며 UnityPy가 필요합니다.

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
