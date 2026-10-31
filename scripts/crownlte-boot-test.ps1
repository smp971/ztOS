param(
    [Parameter(Mandatory=$true)][string]$Adb,
    [Parameter(Mandatory=$true)][string]$Backups,
    [string]$Serial,
    [ValidateSet('Inspect','BootTest','Restore')][string]$Mode = 'Inspect',
    [switch]$StorageTest,
    [switch]$TouchTest,
    [switch]$SystemTest,
    [switch]$GpuTest,
    [switch]$RadiosTest,
    [switch]$PersistentTest,
    [switch]$WritableState,
    [string]$PreviousImage,
    [string]$PreviousDtb,
    [switch]$PreviousPersistent,
    [ValidateSet('system','gpu','radios')][string]$PreviousStage = 'system',
    [string]$ImagePath,
    [string]$DtbPath
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$image = Join-Path $repo 'out\crownlte-rescue.img'
if ($ImagePath) { $image = $ImagePath }
$dtb = if ($DtbPath) { $DtbPath } else { Join-Path $repo 'out\crownlte-rescue.dtb' }
$backup = Join-Path $Backups 'BOOT.img'
$targetSerial = $null

function Invoke-AdbText {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AdbArgs)
    if ($targetSerial) { $result = & $Adb -s $targetSerial @AdbArgs }
    else { $result = & $Adb @AdbArgs }
    if ($LASTEXITCODE -ne 0) { throw "ADB failed: $AdbArgs" }
    return ($result -join "`n").Trim()
}

# Operate only on one connected phone, in root recovery. No Android /data,
# RECOVERY, EFS, partition table or firmware partition is written.
$devices = Invoke-AdbText @('devices')
$rows = @($devices -split "`n" | Where-Object { $_ -match '^\S+\s+(device|recovery|unauthorized|offline)\b' })
if ($Serial) {
    $rows = @($rows | Where-Object { ($_ -split '\s+')[0] -eq $Serial })
}
if ($rows.Count -ne 1) { throw 'Connect exactly one ADB device.' }
$targetSerial = ($rows[0] -split '\s+')[0]
if ((Invoke-AdbText @('get-state')) -ne 'recovery') { throw 'Start Lineage Recovery and enable ADB first.' }
if ((Invoke-AdbText @('shell','getprop ro.product.device')) -ne 'crownlte') { throw 'Not a crownlte.' }
if ((Invoke-AdbText @('shell','getprop ro.product.model')) -ne 'SM-N960F') { throw 'Not the validated SM-N960F model.' }
if ((Invoke-AdbText @('shell','id -u')) -ne '0') { throw 'Recovery ADB is not root.' }
if ((Invoke-AdbText @('shell','readlink -f /dev/block/by-name/BOOT')) -ne '/dev/block/sda10') { throw 'Unexpected BOOT mapping.' }
if ((Invoke-AdbText @('shell','blockdev --getsize64 /dev/block/by-name/BOOT')) -ne '57671680') { throw 'Unexpected BOOT size.' }

$manifest = Get-Content -LiteralPath (Join-Path $Backups 'sha256.json') -Raw | ConvertFrom-Json
$entry = @($manifest | Where-Object { [IO.Path]::GetFileName($_.Path) -eq 'BOOT.img' })
if ($entry.Count -ne 1) { throw 'BOOT backup hash missing from manifest.' }
$backupHash = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($backupHash -ne $entry[0].Hash.ToLowerInvariant()) { throw 'BOOT backup no longer matches its manifest.' }
$recoveryEntry = @($manifest | Where-Object { [IO.Path]::GetFileName($_.Path) -eq 'RECOVERY.img' })
$recoveryHash = (Invoke-AdbText @('shell','sha256sum /dev/block/by-name/RECOVERY')).Split(' ')[0]
if ($recoveryEntry.Count -ne 1 -or $recoveryHash -ne $recoveryEntry[0].Hash.ToLowerInvariant()) { throw 'RECOVERY changed since backup.' }

if ($Mode -ne 'Restore') {
    if ($PersistentTest -and -not ($SystemTest -or $GpuTest -or $RadiosTest)) { throw 'Persistent mode requires a userspace stage.' }
    if ($PreviousPersistent -and -not $PreviousImage) { throw 'PreviousPersistent requires PreviousImage.' }
    $selectedStages = @(@($StorageTest,$TouchTest,$SystemTest,$GpuTest,$RadiosTest) | Where-Object { $_ })
    if ($selectedStages.Count -gt 1) { throw 'Select one test stage.' }
    if (($StorageTest -and $TouchTest) -or ($StorageTest -and $SystemTest) -or ($TouchTest -and $SystemTest)) { throw 'Select one test stage.' }
    $stage = if ($RadiosTest) { 'radios' } elseif ($GpuTest) { 'gpu' } elseif ($SystemTest) { 'system' } elseif ($TouchTest) { 'touch' } elseif ($StorageTest) { 'storage' } else { 'usb' }
    [string[]]$verifyMode = @()
    if ($PersistentTest) { $verifyMode = @('--persistent') }
    if ($WritableState) { $verifyMode += '--writable-state' }
    & python (Join-Path $PSScriptRoot 'verify-crownlte.py') --stock-dtb (Join-Path $Backups 'running.dtb') --dtb $dtb --image $image --reference (Join-Path $Backups 'RECOVERY.img') --stage $stage @verifyMode
    if ($LASTEXITCODE -ne 0) { throw 'Rescue image verification failed.' }
    $currentHash = (Invoke-AdbText @('shell','sha256sum /dev/block/by-name/BOOT')).Split(' ')[0]
    if ($currentHash -ne $backupHash) {
        if (-not $PreviousImage) { throw 'BOOT changed since backup; inspect or restore first.' }
        $priorDtb = if ($PreviousDtb) { $PreviousDtb } else { [IO.Path]::ChangeExtension($PreviousImage, '.dtb') }
        [string[]]$priorMode = @()
        if ($PreviousPersistent) { $priorMode = @('--persistent') }
        & python (Join-Path $PSScriptRoot 'verify-crownlte.py') --stock-dtb (Join-Path $Backups 'running.dtb') --dtb $priorDtb --image $PreviousImage --reference (Join-Path $Backups 'RECOVERY.img') --stage $PreviousStage @priorMode
        if ($LASTEXITCODE -ne 0) { throw 'Previous image verification failed.' }
        $expectedPartition = [IO.File]::ReadAllBytes($backup)
        $previousBytes = [IO.File]::ReadAllBytes($PreviousImage)
        [Array]::Copy($previousBytes, 0, $expectedPartition, 0, $previousBytes.Length)
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $expectedCurrent = [BitConverter]::ToString($hasher.ComputeHash($expectedPartition)).Replace('-','').ToLowerInvariant() }
        finally { $hasher.Dispose() }
        if ($currentHash -ne $expectedCurrent) { throw 'BOOT does not match the previous verified test plus original partition tail.' }
    }
}
if ($Mode -eq 'Inspect') {
    Write-Output 'READY: target, recovery, backup and rescue image checked. No partition written.'
    return
}

$payload = $backup
$temporaryPayload = $null
if ($Mode -ne 'Restore') {
    $sourceBytes = [IO.File]::ReadAllBytes($image)
    if ($sourceBytes.Length -gt 57671680) { throw 'Image exceeds BOOT.' }
    # Canonicalize the untouched tail, even when replacing a larger test image.
    $partitionBytes = [IO.File]::ReadAllBytes($backup)
    [Array]::Copy($sourceBytes, 0, $partitionBytes, 0, $sourceBytes.Length)
    $temporaryPayload = [IO.Path]::GetTempFileName()
    [IO.File]::WriteAllBytes($temporaryPayload, $partitionBytes)
    $payload = $temporaryPayload
    Write-Output ('Image SHA256: ' + (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant())
}
try {
$expectedHash = (Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item -LiteralPath $payload).Length
if ($size -gt 57671680) { throw 'Payload exceeds BOOT.' }
Invoke-AdbText @('push',$payload,'/tmp/crownlte-boot.img') | Write-Output
$copyHash = (Invoke-AdbText @('shell','sha256sum /tmp/crownlte-boot.img')).Split(' ')[0]
if ($copyHash -ne $expectedHash) { throw 'USB copy hash mismatch.' }
Invoke-AdbText @('shell','dd if=/tmp/crownlte-boot.img of=/dev/block/by-name/BOOT bs=1048576 conv=fsync') | Write-Output
$readbackHash = (Invoke-AdbText @('shell',"head -c $size /dev/block/by-name/BOOT | sha256sum")).Split(' ')[0]
if ($readbackHash -ne $expectedHash) { throw 'BOOT READBACK MISMATCH. Stay in recovery and restore the backup.' }
Write-Output "BOOT $Mode verified: $expectedHash ($size bytes)."
Invoke-AdbText @('shell','rm /tmp/crownlte-boot.img') | Out-Null
} finally {
    if ($temporaryPayload) { Remove-Item -LiteralPath $temporaryPayload -Force }
}
if ($Mode -eq 'BootTest') {
    if ($PersistentTest) { Write-Output 'Starting persistent ztOS prototype. Automatic test deadline disabled; recovery fallback remains armed.' }
    else { Write-Output 'Starting bounded rescue test; recovery fallback is armed. Restore BOOT after collecting logs.' }
    Invoke-AdbText @('reboot') | Write-Output
} else {
    Write-Output 'Original BOOT restored. Recovery remains open; reboot when ready.'
}
