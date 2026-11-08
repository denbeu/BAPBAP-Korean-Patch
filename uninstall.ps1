[CmdletBinding()]
param([string]$GameDir)

$ErrorActionPreference = 'Stop'
$BuildId = '19658140'
$Expected = @{
    shared_original    = 'D12138D2993DCEECA051DDCC3E1FFCDA49A87668DBBA05BACC7E3537FA9C5D67'
    shared_v1          = 'D05D9A0210B72A3CACBA146AF146EA9680A68770C12CC84277D388A69F49E6EE'
    shared_v2          = '11E78ED6794566B223450118357A2D8C623F7831BC76B28EB93A49D4C914161F'
    level0_original    = '5885DE2731C43B222D8BD367AEF91503145753BC8B0C1187469E4B8048E36B11'
    level0_v1          = '0F9944F516B9AF57EC90E73A82FB4E137151B4E06B5D7A9852FEE232E067C68D'
    level0_v2          = '2DC9C01C07FFBD878EE6155756095065CB462F364C48DEADDB6487D0C7BFC075'
    ga_original        = '75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69'
    ga_v1              = 'BB7F8A6A46FF8C1BEB4B9D97F4EB0F6952ECB283592DCD929EB11CDFCD6DA413'
    ga_v2              = '775735C873581D8BDEA90AD18615FAA44226D7A3F44A0486009852BD7C49BB09'
    ga_stat            = 'C5FEC8A916C82E5B372FFA03F4C42B11B4489405BF805D5E81DCEE778610E79D'
    resources_original = 'D22FD380E83EDE2B5C261C6F45CAE9E19B35FE2D667BF7EF9F31FA981DE3E7D8'
    resources_v2       = 'E7D222A7B788F934000AD98D2F3F01A9D6EEEE7AD3922768C9CA068F944E60B1'
    metadata_original  = 'A159A9F1D5CB9F3F20DFDB64C7C9773D44B0E8428227EA19913D801D19158757'
    metadata_v2        = '6920680D5A5CDCC3653015FEA7E40B8AAB8CEC785587865DD0BA76D418206E47'
}

function Get-Hash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

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
        if ((Test-Path -LiteralPath (Join-Path $full 'bapbap.exe')) -and
            (Test-Path -LiteralPath (Join-Path $full 'bapbap_Data\sharedassets0.assets'))) {
            return $full
        }
    }
    throw 'BAPBAP installation was not found. Re-run with -GameDir "X:\...\BAPBAP".'
}

$GameDir = Resolve-GameDir $GameDir
foreach ($p in @(Get-Process -Name 'bapbap' -ErrorAction SilentlyContinue)) {
    if (-not $p.Path -or $p.Path.StartsWith($GameDir + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'BAPBAP is running. Close the game before uninstalling.'
    }
}
$Targets = @{
    shared    = Join-Path $GameDir 'bapbap_Data\sharedassets0.assets'
    level0    = Join-Path $GameDir 'bapbap_Data\level0'
    ga        = Join-Path $GameDir 'GameAssembly.dll'
    resources = Join-Path $GameDir 'bapbap_Data\resources.assets'
    metadata  = Join-Path $GameDir 'bapbap_Data\il2cpp_data\Metadata\global-metadata.dat'
}
$BackupOriginal = Join-Path $GameDir ('.bapko-backup\build-' + $BuildId)
$BackupV1 = Join-Path $GameDir '.bapko-backup\v1'

# Steam originals when available; otherwise the v1 state saved by the v2 installer.
$useOriginal = Test-Path -LiteralPath (Join-Path $BackupOriginal 'sharedassets0.assets.original')
if ($useOriginal) {
    $Dir = $BackupOriginal; $Suffix = 'original'; $Goal = 'original'
} elseif (Test-Path -LiteralPath (Join-Path $BackupV1 'sharedassets0.assets.v1')) {
    $Dir = $BackupV1; $Suffix = 'v1'; $Goal = 'v1'
} else {
    throw "No backup found under $(Join-Path $GameDir '.bapko-backup'). Use Steam 'Verify integrity of game files' instead."
}
$Sources = @{
    shared    = Join-Path $Dir "sharedassets0.assets.$Suffix"
    level0    = Join-Path $Dir "level0.$Suffix"
    ga        = Join-Path $Dir "GameAssembly.dll.$Suffix"
    resources = Join-Path $BackupOriginal 'resources.assets.original'
    metadata  = Join-Path $BackupOriginal 'global-metadata.dat.original'
}
$Goals = @{
    shared    = $Expected["shared_$Goal"]
    level0    = $Expected["level0_$Goal"]
    ga        = $Expected["ga_$Goal"]
    resources = $Expected.resources_original
    metadata  = $Expected.metadata_original
}

foreach ($k in $Sources.Keys) {
    if (-not (Test-Path -LiteralPath $Sources[$k] -PathType Leaf)) { throw "Backup missing: $($Sources[$k])" }
    if ((Get-Hash $Sources[$k]) -ne $Goals[$k]) { throw "Backup hash does not match the expected state: $($Sources[$k])" }
}
$Known = @{
    shared    = @($Expected.shared_original,$Expected.shared_v1,$Expected.shared_v2)
    level0    = @($Expected.level0_original,$Expected.level0_v1,$Expected.level0_v2)
    ga        = @($Expected.ga_original,$Expected.ga_v1,$Expected.ga_v2,$Expected.ga_stat)
    resources = @($Expected.resources_original,$Expected.resources_v2)
    metadata  = @($Expected.metadata_original,$Expected.metadata_v2)
}
foreach ($k in $Targets.Keys) {
    if ((Get-Hash $Targets[$k]) -notin $Known[$k]) { throw 'Current files are unknown/modified; refusing to overwrite.' }
}

foreach ($k in $Targets.Keys) { Copy-Item -LiteralPath $Sources[$k] -Destination $Targets[$k] -Force }
foreach ($k in $Targets.Keys) {
    if ((Get-Hash $Targets[$k]) -ne $Goals[$k]) { throw 'Restore verification failed.' }
}

if ($Goal -eq 'original') {
    Write-Host "Original BAPBAP files restored successfully: $GameDir"
} else {
    Write-Host "Restored the previous patch (v1) state: $GameDir"
    Write-Host "To get the Steam originals back, use Steam 'Verify integrity of game files'."
}
