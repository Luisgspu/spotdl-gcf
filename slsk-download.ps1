# slsk-download.ps1 — Download a Spotify playlist via Soulseek
# Priority 1: FLAC (lossless)   Priority 2: MP3 320 kbps+
#
# Usage:
#   .\slsk-download.ps1 "https://open.spotify.com/playlist/..."   # Spotify URL (needs API creds)
#   .\slsk-download.ps1 ".\playlist.csv"                          # Exportify CSV (no auth needed)
#   .\slsk-download.ps1 "Artist - Track Title"                    # single track search
#
# CSV mode — export from https://exportify.net then:
#   .\slsk-download.ps1 ".\playlist.csv"

param(
    [Parameter(Mandatory = $true)]
    [string]$Query
)

# ── Load .env ──────────────────────────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*[^#\s]' } | ForEach-Object {
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            $key = $parts[0].Trim()
            $val = $parts[1].Trim().Trim('"')
            Set-Item -Path "env:$key" -Value $val
        }
    }
}

# ── Validate Soulseek credentials ─────────────────────────────────────────────
$missing = @()
if (-not $env:SOULSEEK_USERNAME) { $missing += "SOULSEEK_USERNAME" }
if (-not $env:SOULSEEK_PASSWORD) { $missing += "SOULSEEK_PASSWORD" }
if ($missing.Count -gt 0) {
    Write-Error "Missing in .env: $($missing -join ', ')"
    exit 1
}

$sldl   = "$env:LOCALAPPDATA\Programs\sldl\sldl.exe"
$config = Join-Path $PSScriptRoot "sldl.conf"

function Invoke-SldlTrack([string]$TrackQuery) {
    $sldlArgs = @(
        $TrackQuery,
        "--config",          $config,
        "--user",            $env:SOULSEEK_USERNAME,
        "--pass",            $env:SOULSEEK_PASSWORD,
        "--search-timeout", "15000"
    )
    & $sldl @sldlArgs
}

function Invoke-TrackList([System.Collections.Generic.List[string]]$tracks) {
    Write-Host "Downloading $($tracks.Count) tracks via Soulseek..."
    Write-Host ""
    $i = 0
    foreach ($track in $tracks) {
        $i++
        Write-Host "[$i/$($tracks.Count)] $track"
        Invoke-SldlTrack $track
        Write-Host ""
    }
    Write-Host "Done. Files saved to: $(Join-Path $PSScriptRoot 'downloads')"
}

# ── CSV file from Exportify ────────────────────────────────────────────────────
if (Test-Path $Query -PathType Leaf) {
    $csv = Import-Csv $Query
    # Exportify columns: "Track Name", "Artist Name(s)" (among others)
    $tracks = [System.Collections.Generic.List[string]]::new()
    foreach ($row in $csv) {
        $artist = if ($row.'Artist Name(s)') { $row.'Artist Name(s)'.Split(',')[0].Trim() }
                  elseif ($row.'Artist Name') { $row.'Artist Name' }
                  else { $null }
        $title  = if ($row.'Track Name') { $row.'Track Name' } else { $null }
        if ($artist -and $title) { $tracks.Add("$artist - $title") }
    }
    if ($tracks.Count -eq 0) {
        Write-Error "No tracks found in CSV. Expected Exportify format with 'Track Name' and 'Artist Name(s)' columns."
        exit 1
    }
    Invoke-TrackList $tracks

# ── Spotify playlist URL → track list via Client Credentials ──────────────────
} elseif ($Query -match 'open\.spotify\.com/playlist/([a-zA-Z0-9]+)') {
    $playlistId = $Matches[1]

    if (-not $env:SPOTIFY_CLIENT_ID -or -not $env:SPOTIFY_CLIENT_SECRET) {
        Write-Error "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET required to resolve Spotify playlists"
        exit 1
    }

    $b64 = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes("$($env:SPOTIFY_CLIENT_ID):$($env:SPOTIFY_CLIENT_SECRET)")
    )
    $tokenResp = Invoke-RestMethod `
        -Uri         "https://accounts.spotify.com/api/token" `
        -Method      POST `
        -Headers     @{ Authorization = "Basic $b64" } `
        -ContentType "application/x-www-form-urlencoded" `
        -Body        "grant_type=client_credentials"

    $authHeader = @{ Authorization = "Bearer $($tokenResp.access_token)" }

    $tracks = [System.Collections.Generic.List[string]]::new()
    $url = "https://api.spotify.com/v1/playlists/$playlistId/tracks?limit=100"

    do {
        $page = Invoke-RestMethod -Uri $url -Headers $authHeader
        foreach ($item in $page.items) {
            if (-not $item.track -or -not $item.track.name) { continue }
            $artist = ($item.track.artists | Select-Object -First 1).name
            $title  = $item.track.name
            $tracks.Add("$artist - $title")
        }
        $url = $page.next
    } while ($url)

    Invoke-TrackList $tracks

# ── Single track / direct search ──────────────────────────────────────────────
} else {
    Invoke-SldlTrack $Query
}
