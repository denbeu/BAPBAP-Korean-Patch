[CmdletBinding()]
param([string]$GameDir, [switch]$DryRun)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildId = '19658140'
$StepTimeoutMs = 15 * 60 * 1000
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
    resources_original = 'D22FD380E83EDE2B5C261C6F45CAE9E19B35FE2D667BF7EF9F31FA981DE3E7D8'
    resources_v2       = 'E7D222A7B788F934000AD98D2F3F01A9D6EEEE7AD3922768C9CA068F944E60B1'
    metadata_original  = 'A159A9F1D5CB9F3F20DFDB64C7C9773D44B0E8428227EA19913D801D19158757'
    metadata_v2        = '6920680D5A5CDCC3653015FEA7E40B8AAB8CEC785587865DD0BA76D418206E47'
    phrase_v1          = '6364BE197E1FFAD5DC57D39E7E92DDBABFEE49FD6858F7CAA5A673787D2D9487'
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

$script:StepNumber = 0
$script:StepTotal = 0
function Write-Step([string]$Label) {
    $script:StepNumber++
    Write-Host ('[{0}/{1}] {2}' -f $script:StepNumber, $script:StepTotal, $Label)
}

# Runs a tool with a time limit. Output goes to files so a stuck child cannot block on a pipe.
function Run([string]$Exe, [string[]]$ToolArgs) {
    $out = Join-Path $Work ('out-' + [guid]::NewGuid().ToString('N'))
    $err = $out + '.err'
    $line = ($ToolArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $p = Start-Process -FilePath $Exe -ArgumentList $line -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    [void]$p.Handle
    if (-not $p.WaitForExit($StepTimeoutMs)) {
        try { $p.Kill() } catch {}
        throw "A patch step did not finish in time and was stopped: $(Split-Path -Leaf $Exe) $($ToolArgs[0])"
    }
    if ($p.ExitCode -ne 0) {
        foreach ($f in @($err,$out)) { if (Test-Path -LiteralPath $f) { Get-Content -LiteralPath $f -Tail 15 | Write-Host } }
        throw "$(Split-Path -Leaf $Exe) failed with exit code $($p.ExitCode)"
    }
    Remove-Item -LiteralPath $out,$err -Force -ErrorAction SilentlyContinue
}

# Runs one asset-tool command and removes the previous intermediate file to limit disk use.
function Invoke-Asset([string]$Label, [string]$Command, [string]$In, [string]$Out, [string[]]$Extra) {
    Write-Step $Label
    Run $AssetTool (@($Command,'--input',$In,'--output',$Out) + $Extra)
    if ($In.StartsWith($Work, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $In -Force }
}

function Read-JsonFile([string]$Path) { [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json }

function ConvertFrom-Hex([string]$Hex) {
    $bytes = New-Object byte[] ($Hex.Length / 2)
    for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [Convert]::ToByte($Hex.Substring($i * 2, 2), 16) }
    return ,$bytes
}

# Applies guarded byte edits generated by the source/ scripts.
function Invoke-GameAssemblyEdits([string]$InFile, [string]$OutFile, [string]$SpecPath) {
    $spec = Read-JsonFile $SpecPath
    if ((Get-Hash $InFile) -ne $spec.input_sha256) { throw 'GameAssembly edit list does not match the input file.' }
    $data = [IO.File]::ReadAllBytes($InFile)
    foreach ($e in $spec.edits) {
        $old = ConvertFrom-Hex $e.expected
        $new = ConvertFrom-Hex $e.replacement
        for ($i = 0; $i -lt $old.Length; $i++) {
            if ($data[[int64]$e.offset + $i] -ne $old[$i]) { throw "GameAssembly guard failed: $($e.name)" }
        }
        [Array]::Copy($new, 0, $data, [int64]$e.offset, $new.Length)
    }
    $tail = ConvertFrom-Hex $spec.append
    $fs = [IO.File]::Open($OutFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $fs.Write($data, 0, $data.Length); $fs.Write($tail, 0, $tail.Length) } finally { $fs.Dispose() }
}

# Points selected string literals at new UTF-8 data appended to the end of global-metadata.dat.
function Invoke-MetadataLiterals([string]$InFile, [string]$OutFile, [string]$SpecPath) {
    $spec = Read-JsonFile $SpecPath
    $data = [IO.File]::ReadAllBytes($InFile)
    if ([BitConverter]::ToUInt32($data, 0) -ne [uint32]4205910959) { throw 'Unexpected global-metadata.dat signature.' }
    $tableOff = [BitConverter]::ToInt32($data, 8)
    $dataOff = [BitConverter]::ToInt32($data, 16)
    $utf8 = New-Object Text.UTF8Encoding($false)
    $extra = New-Object IO.MemoryStream
    foreach ($l in $spec.literals) {
        $entry = $tableOff + 8 * [int]$l.index
        $len = [BitConverter]::ToInt32($data, $entry)
        $idx = [BitConverter]::ToInt32($data, $entry + 4)
        if ($utf8.GetString($data, $dataOff + $idx, $len) -cne $l.original) { throw "Metadata literal guard failed: $($l.index)" }
        $new = $utf8.GetBytes($l.patched)
        $newIdx = [int]($data.Length + $extra.Length - $dataOff)
        $extra.Write($new, 0, $new.Length)
        [Array]::Copy([BitConverter]::GetBytes([int]$new.Length), 0, $data, $entry, 4)
        [Array]::Copy([BitConverter]::GetBytes($newIdx), 0, $data, $entry + 4, 4)
    }
    $fs = [IO.File]::Open($OutFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $fs.Write($data, 0, $data.Length); $extra.WriteTo($fs) } finally { $fs.Dispose() }
}

# Decides each file on its own, so an interrupted install can continue. A file that matches no known
# state, such as one left half written, is taken from a verified backup when one exists.
function Get-FileState($Item) {
    $hash = Get-Hash $Item.Path
    foreach ($state in 'v2','v1','original') {
        $want = $Expected["$($Item.Key)_$state"]
        if ($want -and $hash -eq $want) { return @{ State=$state; Input=$Item.Path; FromBackup=$false; Hash=$hash } }
    }
    $originalBackup = Join-Path $BackupOriginal ($Item.Name + '.original')
    if ((Test-Path -LiteralPath $originalBackup) -and (Get-Hash $originalBackup) -eq $Expected["$($Item.Key)_original"]) {
        return @{ State='original'; Input=$originalBackup; FromBackup=$true; Hash=$hash }
    }
    $v1Backup = Join-Path $BackupV1 ($Item.Name + '.v1')
    if ($Expected["$($Item.Key)_v1"] -and (Test-Path -LiteralPath $v1Backup) -and (Get-Hash $v1Backup) -eq $Expected["$($Item.Key)_v1"]) {
        return @{ State='v1'; Input=$v1Backup; FromBackup=$true; Hash=$hash }
    }
    return @{ State='unknown'; Input=$null; FromBackup=$false; Hash=$hash }
}

# Copies to a temporary name first, so an interruption never leaves a partial file under the real name.
function Copy-Atomic([string]$From, [string]$To) {
    $tmp = $To + '.bapko-new'
    Copy-Item -LiteralPath $From -Destination $tmp -Force
    Move-Item -LiteralPath $tmp -Destination $To -Force
}

function Save-Backup($Item, $Info) {
    if ($Info.FromBackup -or $Info.State -eq 'v2') { return }
    $dir = if ($Info.State -eq 'original') { $BackupOriginal } else { $BackupV1 }
    $target = Join-Path $dir ($Item.Name + '.' + $Info.State)
    if ((Test-Path -LiteralPath $target) -and (Get-Hash $target) -eq $Info.Hash) { return }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Copy-Atomic $Item.Path $target
    if ((Get-Hash $target) -ne $Info.Hash) { throw 'Backup validation failed; game files were not replaced.' }
}

$GameDir = Resolve-GameDir $GameDir
if (-not $DryRun) {
    # A process whose path cannot be read is treated as this copy of the game.
    foreach ($p in @(Get-Process -Name 'bapbap' -ErrorAction SilentlyContinue)) {
        if (-not $p.Path -or $p.Path.StartsWith($GameDir + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'BAPBAP is running. Close the game before installing the patch.' }
    }
}
$BackupRoot = Join-Path $GameDir '.bapko-backup'
$BackupOriginal = Join-Path $BackupRoot ('build-' + $BuildId)
$BackupV1 = Join-Path $BackupRoot 'v1'
$Items = @(
    @{ Key='shared';    Name='sharedassets0.assets'; Path=(Join-Path $GameDir 'bapbap_Data\sharedassets0.assets') }
    @{ Key='level0';    Name='level0';               Path=(Join-Path $GameDir 'bapbap_Data\level0') }
    @{ Key='ga';        Name='GameAssembly.dll';     Path=(Join-Path $GameDir 'GameAssembly.dll') }
    @{ Key='resources'; Name='resources.assets';     Path=(Join-Path $GameDir 'bapbap_Data\resources.assets') }
    @{ Key='metadata';  Name='global-metadata.dat';  Path=(Join-Path $GameDir 'bapbap_Data\il2cpp_data\Metadata\global-metadata.dat') }
)
foreach ($x in $Items) {
    if (-not (Test-Path -LiteralPath $x.Path -PathType Leaf)) { throw "Required game file not found: $($x.Path)" }
    # Temporary file left by an interrupted run.
    Remove-Item -LiteralPath ($x.Path + '.bapko-new') -Force -ErrorAction SilentlyContinue
}

Write-Host 'Checking game files...'
$States = @{}
foreach ($x in $Items) { $States[$x.Key] = Get-FileState $x }
$pending = @($Items | Where-Object { $States[$_.Key].State -ne 'v2' })
if ($pending.Count -eq 0) { Write-Host 'BAPBAP Korean patch v2 is already installed and hashes match.'; exit 0 }
$unknown = @($Items | Where-Object { $States[$_.Key].State -eq 'unknown' })
if ($unknown.Count -gt 0) {
    $lines = ($unknown | ForEach-Object { "$($_.Name)=$($States[$_.Key].Hash)" }) -join "`n"
    throw "Unsupported or modified game files. Verify Steam files first.`n$lines"
}
foreach ($x in $pending) { if ($States[$x.Key].FromBackup) { Write-Host "$($x.Name) does not match a known state; using the verified backup." } }

$V2 = Join-Path $Root 'payload\v2'
$PayloadV1=Join-Path $Root 'payload\korean-full.txt'; $FullSpec=Join-Path $Root 'payload\full_asset_patches.json'; $FontSpec=Join-Path $Root 'payload\font_fallback_patches.json'; $SharedVisualSpec=Join-Path $Root 'payload\visual_qa_shared_patches.json'; $Level0VisualSpec=Join-Path $Root 'payload\visual_qa_level0_patches.json'; $AssetTool=Join-Path $Root 'tools\BapAssetTool\BapAssetTool.exe'
$PayloadV2=Join-Path $V2 'korean-full-v2.txt'; $FontSpecV2=Join-Path $V2 'font_fallback_patches.json'; $SharedV2=Join-Path $V2 'strings_shared.json'; $Level0V2=Join-Path $V2 'strings_level0.json'; $ResourcesV2=Join-Path $V2 'strings_resources.json'; $GaEditsV1=Join-Path $V2 'gameassembly_edits.json'; $GaEditsOriginal=Join-Path $V2 'gameassembly_edits_from_original.json'; $MetaSpec=Join-Path $V2 'metadata_literals.json'
foreach ($x in @($PayloadV1,$FullSpec,$FontSpec,$SharedVisualSpec,$Level0VisualSpec,$AssetTool,$PayloadV2,$FontSpecV2,$SharedV2,$Level0V2,$ResourcesV2,$GaEditsV1,$GaEditsOriginal,$MetaSpec)) { if (-not (Test-Path -LiteralPath $x -PathType Leaf)) { throw "Patch package file missing: $x" } }
if ((Get-Hash $PayloadV1) -ne $Expected.phrase_v1) { throw 'korean-full.txt hash mismatch.' }

$total = 1
$st = $States.shared.State
if ($st -eq 'original') { $total += 7 }
if ($st -ne 'v2') { $total += 4 }
$st = $States.level0.State
if ($st -eq 'original') { $total += 1 }
if ($st -ne 'v2') { $total += 1 }
foreach ($k in 'ga','resources','metadata') { if ($States[$k].State -ne 'v2') { $total += 1 } }
$script:StepTotal = $total

$Work = Join-Path $env:TEMP ('bapko-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$Final = @{}
try {
    $info = $States.shared
    if ($info.State -ne 'v2') {
        $in = $info.Input
        if ($info.State -eq 'original') {
            $a = Join-Path $Work 'a1'; Invoke-Asset 'v1: applying Korean text' 'replace' $in $a @('--path-id','2928','--payload',$PayloadV1)
            $b = Join-Path $Work 'a2'; Invoke-Asset 'v1: applying UI text' 'patch-string-set' $a $b @('--spec',$FullSpec)
            $a = Join-Path $Work 'a3'; Invoke-Asset 'v1: font fallback 1/3' 'patch-font-fallback' $b $a @('--spec',$FontSpec,'--patch-index','0')
            $b = Join-Path $Work 'a4'; Invoke-Asset 'v1: font fallback 2/3' 'patch-font-fallback' $a $b @('--spec',$FontSpec,'--patch-index','1')
            $a = Join-Path $Work 'a5'; Invoke-Asset 'v1: font fallback 3/3' 'patch-font-fallback' $b $a @('--spec',$FontSpec,'--patch-index','2')
            $b = Join-Path $Work 'a6'; Invoke-Asset 'v1: font setting' 'patch-font-setting' $a $b @('--spec',$FontSpec,'--patch-index','0')
            $a = Join-Path $Work 'a7'; Invoke-Asset 'v1: character names' 'patch-string-set' $b $a @('--spec',$SharedVisualSpec)
            if ((Get-Hash $a) -ne $Expected.shared_v1) { throw 'v1 sharedassets0 hash mismatch.' }
            $in = $a
        }
        $a = Join-Path $Work 'b1'; Invoke-Asset 'v2: applying Korean text' 'replace' $in $a @('--path-id','2928','--payload',$PayloadV2)
        $b = Join-Path $Work 'b2'; Invoke-Asset 'v2: font fallback 1/2' 'patch-font-fallback' $a $b @('--spec',$FontSpecV2,'--patch-index','0')
        $a = Join-Path $Work 'b3'; Invoke-Asset 'v2: font fallback 2/2' 'patch-font-fallback' $b $a @('--spec',$FontSpecV2,'--patch-index','1')
        $b = Join-Path $Work 'sharedassets0.assets'; Invoke-Asset 'v2: translating game text' 'patch-string-set' $a $b @('--spec',$SharedV2)
        if ((Get-Hash $b) -ne $Expected.shared_v2) { throw 'Final sharedassets0 hash mismatch.' }
        $Final.shared = $b
    }
    $info = $States.level0
    if ($info.State -ne 'v2') {
        $in = $info.Input
        if ($info.State -eq 'original') {
            $a = Join-Path $Work 'l1'; Invoke-Asset 'v1: training UI text' 'patch-string-set' $in $a @('--spec',$Level0VisualSpec)
            if ((Get-Hash $a) -ne $Expected.level0_v1) { throw 'v1 level0 hash mismatch.' }
            $in = $a
        }
        $b = Join-Path $Work 'level0'; Invoke-Asset 'v2: translating scene text' 'patch-string-set' $in $b @('--spec',$Level0V2)
        if ((Get-Hash $b) -ne $Expected.level0_v2) { throw 'Final level0 hash mismatch.' }
        $Final.level0 = $b
    }
    $info = $States.resources
    if ($info.State -ne 'v2') {
        $b = Join-Path $Work 'resources.assets'; Invoke-Asset 'v2: translating map text' 'patch-string-set' $info.Input $b @('--spec',$ResourcesV2)
        if ((Get-Hash $b) -ne $Expected.resources_v2) { throw 'Final resources.assets hash mismatch.' }
        $Final.resources = $b
    }
    $info = $States.ga
    if ($info.State -ne 'v2') {
        Write-Step 'v2: patching GameAssembly.dll'
        $b = Join-Path $Work 'GameAssembly.dll'
        $edits = if ($info.State -eq 'original') { $GaEditsOriginal } else { $GaEditsV1 }
        Invoke-GameAssemblyEdits $info.Input $b $edits
        if ((Get-Hash $b) -ne $Expected.ga_v2) { throw 'Final GameAssembly hash mismatch.' }
        $Final.ga = $b
    }
    $info = $States.metadata
    if ($info.State -ne 'v2') {
        Write-Step 'v2: translating code text'
        $b = Join-Path $Work 'global-metadata.dat'
        Invoke-MetadataLiterals $info.Input $b $MetaSpec
        if ((Get-Hash $b) -ne $Expected.metadata_v2) { throw 'Final global-metadata hash mismatch.' }
        $Final.metadata = $b
    }
    if ($DryRun) { Write-Host 'Dry-run PASS: all patched outputs reproduced the verified final hashes. No game files were changed.'; return }

    Write-Step 'Backing up and replacing game files'
    foreach ($x in $pending) { Save-Backup $x $States[$x.Key] }
    foreach ($x in $pending) {
        Copy-Item -LiteralPath $Final[$x.Key] -Destination ($x.Path + '.bapko-new') -Force
        if ((Get-Hash ($x.Path + '.bapko-new')) -ne $Expected["$($x.Key)_v2"]) { throw "Copy verification failed: $($x.Name)" }
    }
    # Everything is verified on the game drive; the renames below are quick and atomic per file.
    foreach ($x in $pending) { Move-Item -LiteralPath ($x.Path + '.bapko-new') -Destination $x.Path -Force }
    foreach ($x in $Items) { if ((Get-Hash $x.Path) -ne $Expected["$($x.Key)_v2"]) { throw "Post-install hash verification failed: $($x.Name)" } }
    Write-Host "Installed BAPBAP Korean patch v2 successfully: $GameDir"; Write-Host "Backups: $BackupRoot"
} finally {
    if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue }
    foreach ($x in $Items) { Remove-Item -LiteralPath ($x.Path + '.bapko-new') -Force -ErrorAction SilentlyContinue }
}
