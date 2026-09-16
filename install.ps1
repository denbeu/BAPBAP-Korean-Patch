[CmdletBinding()]
param([string]$GameDir, [switch]$DryRun)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildId = '19658140'
$Expected = @{
    shared_original = 'D12138D2993DCEECA051DDCC3E1FFCDA49A87668DBBA05BACC7E3537FA9C5D67'
    shared_patched  = '8DED259B437AB6DE69466C25D535EFD4F6CF312FB4FE919D5842065CC60A6064'
    level0_original = '5885DE2731C43B222D8BD367AEF91503145753BC8B0C1187469E4B8048E36B11'
    level0_patched  = '0F9944F516B9AF57EC90E73A82FB4E137151B4E06B5D7A9852FEE232E067C68D'
    ga_original     = '75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69'
    ga_patched      = '9763C4FF7EE9DA98D3E6E9A8ABE1B693B56B186FC321471AA163A1BC22965E18'
    phrase          = '89C4B0BC4237F577C5783C46875085CF8D7A2227A2B574FFD10CA13BCAF822E5'
}
function Get-Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }
function Resolve-GameDir([string]$Requested) {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($Requested) { $candidates.Add($Requested) }
    $candidates.Add((Get-Location).Path)
    try {
        $steamPath = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction Stop).SteamPath
        if ($steamPath) {
            $candidates.Add((Join-Path $steamPath 'steamapps\common\BAPBAP'))
            $vdf = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf) {
                $text = Get-Content -LiteralPath $vdf -Raw
                foreach ($m in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
                    $lib = $m.Groups[1].Value -replace '\\\\','\'
                    $candidates.Add((Join-Path $lib 'steamapps\common\BAPBAP'))
                }
            }
        }
    } catch {}
    $candidates.Add('C:\Program Files (x86)\Steam\steamapps\common\BAPBAP')
    $candidates.Add('C:\Program Files\Steam\steamapps\common\BAPBAP')
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $full = [IO.Path]::GetFullPath($candidate)
        if ((Test-Path -LiteralPath (Join-Path $full 'bapbap.exe')) -and (Test-Path -LiteralPath (Join-Path $full 'bapbap_Data\sharedassets0.assets'))) { return $full }
    }
    throw 'BAPBAP installation was not found. Re-run with -GameDir "X:\...\BAPBAP".'
}
function Run([string]$Exe, [string[]]$ToolArgs) { & $Exe @ToolArgs; if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" } }

if (-not $DryRun -and (Get-Process -Name 'bapbap' -ErrorAction SilentlyContinue)) { throw 'BAPBAP is running. Close the game before installing the patch.' }
$GameDir = Resolve-GameDir $GameDir
$Shared = Join-Path $GameDir 'bapbap_Data\sharedassets0.assets'
$Level0 = Join-Path $GameDir 'bapbap_Data\level0'
$GameAssembly = Join-Path $GameDir 'GameAssembly.dll'
foreach ($x in @($Shared,$Level0,$GameAssembly)) { if (-not (Test-Path -LiteralPath $x -PathType Leaf)) { throw "Required game file not found: $x" } }
$sharedHash=Get-Hash $Shared; $level0Hash=Get-Hash $Level0; $gaHash=Get-Hash $GameAssembly
if ($sharedHash -eq $Expected.shared_patched -and $level0Hash -eq $Expected.level0_patched -and $gaHash -eq $Expected.ga_patched) { Write-Host 'BAPBAP Korean patch is already installed and hashes match.'; exit 0 }
if ($sharedHash -ne $Expected.shared_original -or $level0Hash -ne $Expected.level0_original -or $gaHash -ne $Expected.ga_original) { throw "Unsupported or modified game files. Verify Steam files first.
sharedassets0=$sharedHash
level0=$level0Hash
GameAssembly=$gaHash" }

$Payload=Join-Path $Root 'payload\korean-full.txt'; $FullSpec=Join-Path $Root 'payload\full_asset_patches.json'; $FontSpec=Join-Path $Root 'payload\font_fallback_patches.json'; $SharedVisualSpec=Join-Path $Root 'payload\visual_qa_shared_patches.json'; $Level0VisualSpec=Join-Path $Root 'payload\visual_qa_level0_patches.json'; $AssetTool=Join-Path $Root 'tools\BapAssetTool\BapAssetTool.exe'; $GameAssemblyPatcher=Join-Path $Root 'tools\GameAssemblyPatcher.exe'
foreach ($x in @($Payload,$FullSpec,$FontSpec,$SharedVisualSpec,$Level0VisualSpec,$AssetTool,$GameAssemblyPatcher)) { if (-not (Test-Path -LiteralPath $x -PathType Leaf)) { throw "Patch package file missing: $x" } }
if ((Get-Hash $Payload) -ne $Expected.phrase) { throw 'korean-full.txt hash mismatch.' }

$Work=Join-Path $env:TEMP ('bapko-' + [guid]::NewGuid().ToString('N')); $Backup=Join-Path $GameDir ('.bapko-backup\build-' + $BuildId)
New-Item -ItemType Directory -Force -Path $Work | Out-Null
try {
    $s1=Join-Path $Work 'shared.1.assets'; $s2=Join-Path $Work 'shared.2.assets'; $s3=Join-Path $Work 'shared.3.assets'; $s4=Join-Path $Work 'shared.4.assets'; $s5=Join-Path $Work 'shared.5.assets'; $s6=Join-Path $Work 'shared.6.assets'; $sFinal=Join-Path $Work 'sharedassets0.assets'
    Run $AssetTool @('replace','--input',$Shared,'--output',$s1,'--path-id','2928','--payload',$Payload)
    Run $AssetTool @('patch-string-set','--input',$s1,'--output',$s2,'--spec',$FullSpec)
    Run $AssetTool @('patch-font-fallback','--input',$s2,'--output',$s3,'--spec',$FontSpec,'--patch-index','0')
    Run $AssetTool @('patch-font-fallback','--input',$s3,'--output',$s4,'--spec',$FontSpec,'--patch-index','1')
    Run $AssetTool @('patch-font-fallback','--input',$s4,'--output',$s5,'--spec',$FontSpec,'--patch-index','2')
    Run $AssetTool @('patch-font-setting','--input',$s5,'--output',$s6,'--spec',$FontSpec,'--patch-index','0')
    Run $AssetTool @('patch-string-set','--input',$s6,'--output',$sFinal,'--spec',$SharedVisualSpec)
    if ((Get-Hash $sFinal) -ne $Expected.shared_patched) { throw 'Final sharedassets0 hash mismatch.' }
    $lFinal=Join-Path $Work 'level0'; Run $AssetTool @('patch-string-set','--input',$Level0,'--output',$lFinal,'--spec',$Level0VisualSpec); if ((Get-Hash $lFinal) -ne $Expected.level0_patched) { throw 'Final level0 hash mismatch.' }
    $gFinal=Join-Path $Work 'GameAssembly.dll'; $gReport=Join-Path $Work 'GameAssembly.patch-report.json'; Run $GameAssemblyPatcher @('--input',$GameAssembly,'--output',$gFinal,'--report',$gReport); if ((Get-Hash $gFinal) -ne $Expected.ga_patched) { throw 'Final GameAssembly hash mismatch.' }
    if ($DryRun) { Write-Host 'Dry-run PASS: all three patched outputs reproduced the verified final hashes. No game files were changed.'; return }
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    $bs=Join-Path $Backup 'sharedassets0.assets.original'; $bl=Join-Path $Backup 'level0.original'; $bg=Join-Path $Backup 'GameAssembly.dll.original'
    if (-not(Test-Path $bs)){Copy-Item $Shared $bs}; if (-not(Test-Path $bl)){Copy-Item $Level0 $bl}; if (-not(Test-Path $bg)){Copy-Item $GameAssembly $bg}
    if ((Get-Hash $bs)-ne $Expected.shared_original -or (Get-Hash $bl)-ne $Expected.level0_original -or (Get-Hash $bg)-ne $Expected.ga_original) { throw 'Backup validation failed; game files were not replaced.' }
    Copy-Item $sFinal $Shared -Force; Copy-Item $lFinal $Level0 -Force; Copy-Item $gFinal $GameAssembly -Force
    if ((Get-Hash $Shared)-ne $Expected.shared_patched -or (Get-Hash $Level0)-ne $Expected.level0_patched -or (Get-Hash $GameAssembly)-ne $Expected.ga_patched) { throw 'Post-install hash verification failed. Use uninstall.ps1 to restore backups.' }
    Write-Host "Installed BAPBAP Korean patch successfully: $GameDir"; Write-Host "Backups: $Backup"
} finally { if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force } }



