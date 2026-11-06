[CmdletBinding()]
param([string]$Output)

# Builds the single-file GUI patcher with the C# compiler that ships with Windows.
$ErrorActionPreference = 'Stop'
$Gui = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $Gui)
if (-not $Output) { $Output = Join-Path $Root 'dist\BAPBAP-Korean-Patcher.exe' }
$Csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $Csc)) { throw "csc.exe not found: $Csc" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null

$bundle = New-Object System.Collections.Generic.List[string]
foreach ($f in 'install.ps1','uninstall.ps1','LICENSE','TRANSLATION_LICENSE.md','THIRD_PARTY_NOTICES.md','tools\BapAssetTool\BapAssetTool.exe','tools\GameAssemblyPatcher.exe') { $bundle.Add($f) }
foreach ($d in 'payload','THIRD_PARTY_LICENSES') {
    Get-ChildItem -LiteralPath (Join-Path $Root $d) -Recurse -File | ForEach-Object { $bundle.Add($_.FullName.Substring($Root.Length + 1)) }
}

$rsp = Join-Path ([IO.Path]::GetTempPath()) ('bapko-gui-' + [guid]::NewGuid().ToString('N') + '.rsp')
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('/nologo')
$lines.Add('/optimize+')
$lines.Add('/target:winexe')
$lines.Add('/platform:x64')
$lines.Add('/codepage:65001')
$lines.Add('/r:System.dll')
$lines.Add('/r:System.Core.dll')
$lines.Add('/r:System.Drawing.dll')
$lines.Add('/r:System.Windows.Forms.dll')
$lines.Add('"/win32manifest:' + (Join-Path $Gui 'app.manifest') + '"')
$lines.Add('"/out:' + $Output + '"')
foreach ($f in $bundle) {
    $full = Join-Path $Root $f
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Bundle file missing: $f" }
    $logical = 'bundle/' + $f.Replace('\', '/')
    $lines.Add('"/resource:' + $full + ',' + $logical + '"')
}
$lines.Add('"' + (Join-Path $Gui 'BapKoreanPatcher.cs') + '"')
[IO.File]::WriteAllLines($rsp, $lines, (New-Object Text.UTF8Encoding($true)))
try {
    & $Csc "@$rsp"
    if ($LASTEXITCODE -ne 0) { throw "csc failed with exit code $LASTEXITCODE" }
} finally {
    Remove-Item -LiteralPath $rsp -Force
}
Write-Host "Built $Output ($($bundle.Count) bundled files)"
