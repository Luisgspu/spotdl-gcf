# check-downloads.ps1 -- Verify which tracks from one or more Exportify CSVs are downloaded
#                        and detect duplicates across playlists.
#
# Usage:
#   .\check-downloads.ps1 "playlist.csv"
#   .\check-downloads.ps1 "playlist1.csv","playlist2.csv"        # cross-playlist dupe check
#   .\check-downloads.ps1 "playlist.csv" -ExportMissing          # writes missing_<name>.csv
#   .\check-downloads.ps1 "playlist.csv" -ExportMissing -Run     # also runs slsk on missing

param(
    [Parameter(Mandatory = $true)]
    [string[]]$CsvFiles,

    [switch]$ExportMissing,   # write missing_<csvname>.csv for each input file
    [switch]$Run              # after exporting, run slsk-download.ps1 on each missing CSV
)

$downloadsDir = Join-Path $PSScriptRoot "downloads"

function Norm([string]$s) {
    ($s.ToLower() -replace "[^a-z0-9]", " " -replace "\s+", " ").Trim()
}

$downloadedNorm = @(Get-ChildItem $downloadsDir -ErrorAction SilentlyContinue |
    ForEach-Object { Norm $_.BaseName })

function Test-Downloaded([string]$artist, [string]$title) {
    $a = Norm $artist
    $t = Norm $title
    $titleWords = $t -split " " | Where-Object { $_.Length -gt 3 }
    foreach ($file in $downloadedNorm) {
        if ($file -notlike "*$a*") { continue }
        $allFound = $true
        foreach ($word in $titleWords) {
            if ($file -notlike "*$word*") { $allFound = $false; break }
        }
        if ($allFound) { return $true }
    }
    return $false
}

# -- Build cross-CSV track index ---------------------------------------------------
$trackIndex = [System.Collections.Generic.Dictionary[string,
    System.Collections.Generic.List[string]]]::new()

foreach ($csvFile in $CsvFiles) {
    if (-not (Test-Path $csvFile)) { Write-Warning "No encontrado: $csvFile"; continue }
    $csvName = Split-Path $csvFile -Leaf
    foreach ($row in (Import-Csv $csvFile)) {
        $artist = if ($row.'Artist Name(s)') { $row.'Artist Name(s)'.Split(',')[0].Trim() } else { $null }
        $title  = if ($row.'Track Name')     { $row.'Track Name' }                           else { $null }
        if (-not $artist -or -not $title) { continue }
        $key = "$artist|||$title"
        if (-not $trackIndex.ContainsKey($key)) {
            $trackIndex[$key] = [System.Collections.Generic.List[string]]::new()
        }
        if ($csvName -notin $trackIndex[$key]) { $trackIndex[$key].Add($csvName) }
    }
}

# -- Classify each track -----------------------------------------------------------
$downloaded = [System.Collections.Generic.List[string]]::new()
$missing    = [System.Collections.Generic.List[psobject]]::new()
$duplicates = [System.Collections.Generic.List[psobject]]::new()

foreach ($key in $trackIndex.Keys) {
    $artist, $title = $key -split "\|\|\|", 2
    $sources = $trackIndex[$key]

    if (Test-Downloaded $artist $title) {
        $downloaded.Add("$artist - $title")
    } else {
        $missing.Add([pscustomobject]@{
            Artist  = $artist
            Title   = $title
            Sources = $sources -join ", "
        })
    }

    if ($sources.Count -gt 1) {
        $duplicates.Add([pscustomobject]@{
            Track     = "$artist - $title"
            AppearsIn = $sources -join ", "
        })
    }
}

# -- Report ------------------------------------------------------------------------
Write-Host ""
Write-Host "DESCARGADAS : $($downloaded.Count)" -ForegroundColor Green
Write-Host "FALTANTES   : $($missing.Count)"    -ForegroundColor Red
Write-Host "DUPLICADAS  : $($duplicates.Count)" -ForegroundColor Yellow
Write-Host ""

if ($missing.Count -gt 0) {
    Write-Host "-- FALTANTES -----------------------------------------------" -ForegroundColor Red
    $missing | ForEach-Object {
        $src = if ($CsvFiles.Count -gt 1) { "  [$($_.Sources)]" } else { "" }
        Write-Host "  $($_.Artist) - $($_.Title)$src"
    }
    Write-Host ""
}

if ($duplicates.Count -gt 0) {
    Write-Host "-- EN MULTIPLES PLAYLISTS ----------------------------------" -ForegroundColor Yellow
    $duplicates | ForEach-Object { Write-Host "  $($_.Track)  ->  $($_.AppearsIn)" }
    Write-Host ""
}

# -- Export missing CSVs -----------------------------------------------------------
if ($ExportMissing -and $missing.Count -gt 0) {
    $exported = @()
    foreach ($csvFile in $CsvFiles) {
        $csvName = Split-Path $csvFile -Leaf
        $forThis = $missing | Where-Object { $_.Sources -match [regex]::Escape($csvName) }
        if ($forThis.Count -eq 0) { continue }

        $outName = "missing_" + [System.IO.Path]::GetFileNameWithoutExtension($csvFile) + ".csv"
        $outPath = Join-Path $PSScriptRoot $outName
        $forThis | ForEach-Object {
            [pscustomobject]@{ "Artist Name(s)" = $_.Artist; "Track Name" = $_.Title }
        } | Export-Csv $outPath -NoTypeInformation -Encoding UTF8
        Write-Host "Exportado: $outPath ($($forThis.Count) tracks)" -ForegroundColor Cyan
        $exported += $outPath
    }

    if ($Run -and $exported.Count -gt 0) {
        $script = Join-Path $PSScriptRoot "slsk-download.ps1"
        foreach ($outPath in $exported) {
            Write-Host ""
            Write-Host "Descargando faltantes: $outPath" -ForegroundColor Cyan
            & $script $outPath
        }
    }
}
