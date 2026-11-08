# Verified patch scope

Supported Steam build: `19658140`

The patch has two layers. v2 is applied on top of the verified v1 output, so installing from the Steam originals and upgrading from an existing v1 install produce identical files.

| File | Steam original SHA-256 | v1 SHA-256 | v2 SHA-256 |
| --- | --- | --- | --- |
| `bapbap_Data/sharedassets0.assets` | `D12138D2993DCEECA051DDCC3E1FFCDA49A87668DBBA05BACC7E3537FA9C5D67` | `D05D9A0210B72A3CACBA146AF146EA9680A68770C12CC84277D388A69F49E6EE` | `11E78ED6794566B223450118357A2D8C623F7831BC76B28EB93A49D4C914161F` |
| `bapbap_Data/level0` | `5885DE2731C43B222D8BD367AEF91503145753BC8B0C1187469E4B8048E36B11` | `0F9944F516B9AF57EC90E73A82FB4E137151B4E06B5D7A9852FEE232E067C68D` | `2DC9C01C07FFBD878EE6155756095065CB462F364C48DEADDB6487D0C7BFC075` |
| `GameAssembly.dll` | `75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69` | `BB7F8A6A46FF8C1BEB4B9D97F4EB0F6952ECB283592DCD929EB11CDFCD6DA413` | `775735C873581D8BDEA90AD18615FAA44226D7A3F44A0486009852BD7C49BB09` |
| `bapbap_Data/resources.assets` | `D22FD380E83EDE2B5C261C6F45CAE9E19B35FE2D667BF7EF9F31FA981DE3E7D8` | unchanged | `E7D222A7B788F934000AD98D2F3F01A9D6EEEE7AD3922768C9CA068F944E60B1` |
| `bapbap_Data/il2cpp_data/Metadata/global-metadata.dat` | `A159A9F1D5CB9F3F20DFDB64C7C9773D44B0E8428227EA19913D801D19158757` | unchanged | `6920680D5A5CDCC3653015FEA7E40B8AAB8CEC785587865DD0BA76D418206E47` |

Korean phrase payload SHA-256:

- v1 `payload/korean-full.txt`: `6364BE197E1FFAD5DC57D39E7E92DDBABFEE49FD6858F7CAA5A673787D2D9487`
- v2 `payload/v2/korean-full-v2.txt`: `B80D91E224CD38CC5F6458C526320397FE3BD966310E9764EC99845A1247E7F7`

## What v2 changes

| Problem | Root cause | Fix |
| --- | --- | --- |
| Hangul nicknames show as boxes in the kill feed, teammate names, and scoreboards | `LiberationSans SDF`, also the TMP default font, was the only UI font whose fallback chain never reached Hangul | Append `NotoSansCJK-Medium-Fallback SDF` to its fallback table (also `0927 SDF`) |
| Friend list drops the last character of a Hangul nickname | `UILobbyFriendEntry.Initialise` checks only the primary font, then removes the last "missing" character from the name | Skip the removal in `GameAssembly.dll`; the fallback font renders the name |
| Stat fragments read in English order (`-150 ♥체력`) | `ItemManager.BuildStatString` concatenates value, icon, then name | Korean slot only: `♥체력 -150`. Damage inside sentences keeps the number before the name with the icon in front (`🗡250 피해를 줍니다`), including ability damage fragments |
| "Disconnected" notice appears mid-match although play continues | The lobby WebSocket and the match WebRTC connection are separate; the notice reports only the lobby socket | Hidden while a match runs. Applies to every locale. A socket that drops mid-match shows no notice after returning to the lobby |
| Berserk/Vengeance cap reads `20% ♥체력` | Hard-coded `{0}% {1}` | Korean slot only: `{1} {0}%` |
| Awkward augment sentences (`받는 피해: 50% 감소`) | Template wording | 36 phrase rows rewritten |
| Untranslated text | `#`-prefixed literals bypass the phrase table; static TMP defaults; string literals in code | 1,125 literal strings, 157 TMP defaults, 66 code literals translated |

The stat-fragment and cap-format changes check the language at runtime, so other locales keep their original text. The friend-list fix applies to every locale. The serialized literal, TMP default, and code-literal translations also apply to every locale because those strings have no per-language data.

Intentionally left in English: stylised item names (`Lock.down`, `Virus.exe`, ...), `HAX`, `XCOM`, `FPS`/`MSAA` labels, and developer-only UI.

## v2 QA state

- phrase rows: `1690`; placeholder and tag identity checked for every phrase, literal, TMP default, and code literal at build time
- object diff against v1: `sharedassets0` 1,572 changed, `level0` 73 changed, `resources` 38 changed, all planned; `0` unexpected; object counts unchanged
- `install.ps1 -DryRun`: PASS on Windows PowerShell 5.1 and PowerShell 7
- install, idempotent re-run, uninstall to v1, and reinstall: PASS
- GUI patcher, driven through its real window on a throwaway folder: install and uninstall PASS
- install from Steam originals on a throwaway folder: PASS with identical v2 hashes. `GameAssembly.dll` and `level0` were rebuilt to the true original hashes. `sharedassets0` used a stand-in with the v1 edits reversed, because the Turkish text is not available locally and the installer overwrites it

Every patched code literal was audited at each use site because a shared literal can also be an identifier. `Occupied` looked like a label but feeds `Animator.StringToHash` in `UICustomLobbyPlayer`; translating it left empty custom-lobby slots showing dummy players, so it was removed. Do not add a code literal without checking what consumes it.

Not localizable from the client: lobby chat notices such as `joined the lobby`, which appear to be sent by the server.

## Optional stat panel (v2.1.0)

`install.ps1 -StatPanel` (the patch tool's checkbox) applies `payload/v2/stat_panel_edits.json` to the v2 `GameAssembly.dll`. Without the switch, a stat panel build is turned back into v2 by applying the same list in reverse. `uninstall.ps1` accepts the stat panel build as a known state.

| File | v2 SHA-256 | v2 + stat panel SHA-256 |
| --- | --- | --- |
| `GameAssembly.dll` | `775735C873581D8BDEA90AD18615FAA44226D7A3F44A0486009852BD7C49BB09` | `C5FEC8A916C82E5B372FFA03F4C42B11B4489405BF805D5E81DCEE778610E79D` |

How it works (`source/mods/stat_panel.py`):

- The first call in `UIManager.Update` (`Screen.get_width`) is redirected to a helper in the `.bapko` section that tail-calls the original. While X is held (legacy `Input.GetKey`), and not while typing in chat, it rebuilds the text on key down and then every 16 frames and shows it through `UITooltip.ShowTooltip`. On key up it calls `UITooltip.HideTooltip`.
- `ShowTooltip(..., fadeIn: false)` leaves a tooltip that faded out earlier at alpha 0, and `fadeIn: true` restarts the fade from 0 on every call, so the helper calls `UIAlphaFade.FadeInInstant` after showing.
- Rows reuse `ItemManager.BuildItemStatStr`, so colors, icons, names, and the v2 word order match the game. Only the panel's damage multiplier row is renamed to `피해 배율` with `String.Replace`.
- Basic attack damage: the slot 0 ability's class is found by its `GetTooltipDescription` vtable entry, and each hit's (damage, scaling) fields are passed to `CharAbilities.GetModifiedDamage` with `isCrit = false`. The fields come from the code that deals the damage, not the tooltips, which use other fields for Eve and leave out hits for several melee combos. Skinny's second hit uses `damage1Scaling`, as the game does.
- The five v2 helpers share one unwind record and sit next to each other, so their exception-table entries are merged into one to make room for the two new helpers.

## v2.0.1 installer changes

The patched files and their hashes are unchanged from v2.0.0.

- `GameAssembly.dll` is patched directly by `install.ps1`, so the PyInstaller step (about two thirds of install time) is gone.
- Each file is judged on its own, and a file matching no known state is taken from a verified backup.
- Backups and replacements are written under a temporary name, verified, then renamed.
- Each tool step has a 15 minute limit.
- The GUI shows step progress and elapsed time, can cancel, stops its workers if it is killed, cleans up work folders left by a killed run, and saves a log to `%LOCALAPPDATA%\BAPBAP-Korean-Patcher\last-run.log`.

See `install.ps1` for the exact chain. `source/patch_gameassembly_v2.py` and `source/build_v2_payload.py` regenerate `payload/v2`.

The user-facing repository ships only the authored patch data/tools needed to reproduce these outputs from a legitimate local installation.
