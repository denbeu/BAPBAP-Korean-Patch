# Verified patch scope

Supported Steam build: `19658140`

| File / payload | Original SHA-256 | Verified patched SHA-256 |
| --- | --- | --- |
| `bapbap_Data/sharedassets0.assets` | `D12138D2993DCEECA051DDCC3E1FFCDA49A87668DBBA05BACC7E3537FA9C5D67` | `D05D9A0210B72A3CACBA146AF146EA9680A68770C12CC84277D388A69F49E6EE` |
| `bapbap_Data/level0` | `5885DE2731C43B222D8BD367AEF91503145753BC8B0C1187469E4B8048E36B11` | `0F9944F516B9AF57EC90E73A82FB4E137151B4E06B5D7A9852FEE232E067C68D` |
| `GameAssembly.dll` | `75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69` | `BB7F8A6A46FF8C1BEB4B9D97F4EB0F6952ECB283592DCD929EB11CDFCD6DA413` |

Korean phrase payload SHA-256:

`6364BE197E1FFAD5DC57D39E7E92DDBABFEE49FD6858F7CAA5A673787D2D9487`

The final QA state used for this package passed:

- phrase rows: `1690`
- strict translation validation: PASS
- glossary validation: `0` issues
- gameplay source-first structural QA: `328` rows, `0` issues
- final `sharedassets0` verifier: `0` issues
- unexpected serialized object changes: `0`
- runtime smoke markers (`Crash`, `Fatal`, `Exception`, `MissingReference`, `NullReference`, `AccessViolation`, TMP missing glyph): `0`
- runtime tooltip visual QA: Sashimi Ultimate and Eve Ultimate placeholder ordering verified after the final fix
- gameplay tooltip placeholder map: `328 / 328` resolved, `0` unresolved

The user-facing repository ships only the authored patch data/tools needed to reproduce these outputs from a legitimate local installation.
