# Verified patch scope

Supported Steam build: `19658140`

| File / payload | Original SHA-256 | Verified patched SHA-256 |
| --- | --- | --- |
| `bapbap_Data/sharedassets0.assets` | `D12138D2993DCEECA051DDCC3E1FFCDA49A87668DBBA05BACC7E3537FA9C5D67` | `8DED259B437AB6DE69466C25D535EFD4F6CF312FB4FE919D5842065CC60A6064` |
| `bapbap_Data/level0` | `5885DE2731C43B222D8BD367AEF91503145753BC8B0C1187469E4B8048E36B11` | `0F9944F516B9AF57EC90E73A82FB4E137151B4E06B5D7A9852FEE232E067C68D` |
| `GameAssembly.dll` | `75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69` | `9763C4FF7EE9DA98D3E6E9A8ABE1B693B56B186FC321471AA163A1BC22965E18` |

Korean phrase payload SHA-256:

`89C4B0BC4237F577C5783C46875085CF8D7A2227A2B574FFD10CA13BCAF822E5`

The final QA state used for this package passed:

- phrase rows: `1690`
- strict translation validation: PASS
- glossary validation: `0` issues
- gameplay source-first structural QA: `328` rows, `0` issues
- final `sharedassets0` verifier: `0` issues
- unexpected serialized object changes: `0`
- runtime smoke markers (`Crash`, `Fatal`, `Exception`, `MissingReference`, `NullReference`, `AccessViolation`, TMP missing glyph): `0`

The user-facing repository ships only the authored patch data/tools needed to reproduce these outputs from a legitimate local installation.
