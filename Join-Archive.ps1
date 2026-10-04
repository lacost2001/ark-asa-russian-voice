$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$metaFile = Join-Path $PSScriptRoot 'parts.json'
if (-not (Test-Path -LiteralPath $metaFile)) { throw 'Download parts.json from the same Release first.' }
$meta = Get-Content -LiteralPath $metaFile -Raw | ConvertFrom-Json
foreach ($part in $meta.parts) {
 if ([IO.Path]::GetFileName($part.name) -ne $part.name) { throw 'Invalid part name' }
 $file = Join-Path $PSScriptRoot $part.name
 if (-not (Test-Path -LiteralPath $file)) { throw "Missing $($part.name)" }
 if ((Get-Item -LiteralPath $file).Length -ne $part.size) { throw "Wrong size: $($part.name)" }
 Write-Host "Checking $($part.name)"
 if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower() -ne $part.sha256) { throw "Checksum mismatch: $($part.name)" }
}
if ([IO.Path]::GetFileName($meta.archive) -ne $meta.archive) { throw 'Invalid archive name' }
$output = Join-Path $PSScriptRoot $meta.archive
if (Test-Path -LiteralPath $output) { throw 'Archive already exists. It has not been overwritten.' }
$temp = $output + '.joining'
$dest = [IO.File]::Open($temp, [IO.FileMode]::CreateNew)
try {
 foreach ($part in $meta.parts) {
  Write-Host "Joining $($part.name)"
  $src = [IO.File]::OpenRead((Join-Path $PSScriptRoot $part.name))
  try { $src.CopyTo($dest) } finally { $src.Dispose() }
 }
} finally { $dest.Dispose() }
if ((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLower() -ne $meta.sha256) { throw 'Final archive checksum mismatch' }
Move-Item -LiteralPath $temp -Destination $output
Write-Host 'Done. Extract the ZIP, then run ASA-Russian-Voice.exe.'
