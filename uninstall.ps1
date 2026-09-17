[CmdletBinding()]
param([string]$GameDir)

$ErrorActionPreference = 'Stop'
$BuildId = '19658140'
$Expected = @{
    shared_original = 'D12138D2993DCEECA051DDCC3E1FFCDA49A87668DBBA05BACC7E3537FA9C5D67'
    shared_patched  = 'D05D9A0210B72A3CACBA146AF146EA9680A68770C12CC84277D388A69F49E6EE'
    level0_original = '5885DE2731C43B222D8BD367AEF91503145753BC8B0C1187469E4B8048E36B11'
    level0_patched  = '0F9944F516B9AF57EC90E73A82FB4E137151B4E06B5D7A9852FEE232E067C68D'
    ga_original     = '75278848FDD7861D3EA7B19E0A9D6397464AC763F39F2B0A5ACB9A7D33385F69'
    ga_patched      = 'BB7F8A6A46FF8C1BEB4B9D97F4EB0F6952ECB283592DCD929EB11CDFCD6DA413'
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

if (Get-Process -Name 'bapbap' -ErrorAction SilentlyContinue) {
    throw 'BAPBAP is running. Close the game before uninstalling.'
}

$GameDir = Resolve-GameDir $GameDir
$Shared = Join-Path $GameDir 'bapbap_Data\sharedassets0.assets'
$Level0 = Join-Path $GameDir 'bapbap_Data\level0'
$GameAssembly = Join-Path $GameDir 'GameAssembly.dll'
$Backup = Join-Path $GameDir ('.bapko-backup\build-' + $BuildId)
$BackupShared = Join-Path $Backup 'sharedassets0.assets.original'
$BackupLevel0 = Join-Path $Backup 'level0.original'
$BackupGameAssembly = Join-Path $Backup 'GameAssembly.dll.original'

foreach ($path in @($BackupShared,$BackupLevel0,$BackupGameAssembly)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Backup missing: $path" }
}
if ((Get-Hash $BackupShared) -ne $Expected.shared_original -or
    (Get-Hash $BackupLevel0) -ne $Expected.level0_original -or
    (Get-Hash $BackupGameAssembly) -ne $Expected.ga_original) {
    throw 'Backup hashes do not match the supported original build.'
}

$sharedCurrent = Get-Hash $Shared
$level0Current = Get-Hash $Level0
$gaCurrent = Get-Hash $GameAssembly
if ($sharedCurrent -notin @($Expected.shared_patched,$Expected.shared_original) -or
    $level0Current -notin @($Expected.level0_patched,$Expected.level0_original) -or
    $gaCurrent -notin @($Expected.ga_patched,$Expected.ga_original)) {
    throw 'Current files are unknown/modified; refusing to overwrite.'
}

Copy-Item -LiteralPath $BackupShared -Destination $Shared -Force
Copy-Item -LiteralPath $BackupLevel0 -Destination $Level0 -Force
Copy-Item -LiteralPath $BackupGameAssembly -Destination $GameAssembly -Force
if ((Get-Hash $Shared) -ne $Expected.shared_original -or
    (Get-Hash $Level0) -ne $Expected.level0_original -or
    (Get-Hash $GameAssembly) -ne $Expected.ga_original) {
    throw 'Restore verification failed.'
}

Write-Host "Original BAPBAP files restored successfully: $GameDir"
