param(
  [int]$Season = 2025,
  [string]$OutJson = $null,
  [string]$OutCsv = $null,
  # Note: SWID should look like '{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}' and espn_s2 is a long URL-encoded token.
  [string]$SWID,
  [string]$EspnS2
)


if (-not $SWID -or -not $EspnS2) {
  Write-Error "Provide -SWID and -EspnS2 (copy cookies from fantasy.espn.com). Example: pwsh .\\download_espn_projections.ps1 -SWID '{...}' -EspnS2 '...'."; exit 1
}

# Enforce TLS1.2+ to avoid handshake issues on older hosts
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}


if (-not $OutJson) { $OutJson = "espn_projections_${Season}.json" }
if (-not $OutCsv) { $OutCsv = "espn_projections_${Season}.csv" }


# Use the players endpoint with players_wl view and scoringPeriodId=0
# The leaguedefaults route does not accept X-Fantasy-Filter for players; using /players avoids 400s
$uri = "https://fantasy.espn.com/apis/v3/games/ffl/seasons/$Season/players?scoringPeriodId=0&view=players_wl"


# Build a valid filter JSON safely
$filter = @{
  players = @{
    # Include free agents and rostered players
    filterStatus = @{ value = @("FREEAGENT","ONTEAM") }
    # common fantasy slots: QB,RB,WR,TE,K,DST
    filterSlotIds = @{ value = @(0,2,3,4,5,16,23) }
    # Sort by season applied total (projections)
    sortAppliedStatTotal = @{
      sortPriority     = 1
      sortAsc          = $false
      statSplitTypeId  = 0
      statCategoryId   = 0
      statSourceId     = 1
      scoringPeriodId  = 0
    }
    limit  = 2000
    offset = 0
  }
  # Critical: request stats payload for season projections
  playerStats = @{
    seasonId        = $Season
    scoringPeriodId = 0
    statSourceId    = 1
    statSplitTypeId = 0
  }
}
$filterJson = $filter | ConvertTo-Json -Compress

# Persist filter for debugging
try {
  $dataDir = Join-Path -Path $PSScriptRoot -ChildPath 'data'
  if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }
  $filterPath = Join-Path $dataDir "espn_filter_${Season}.json"
  Set-Content -Path $filterPath -Value $filterJson -Encoding UTF8
} catch {
  Write-Warning "Could not write filter debug file: $($_.Exception.Message)"
}

$commonHeaders = @{
  'Accept'             = 'application/json'
  'Accept-Language'    = 'en-US,en;q=0.9'
  'User-Agent'         = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
  'Referer'            = 'https://fantasy.espn.com/football/players/projections'
  'Origin'             = 'https://fantasy.espn.com'
  'X-Fantasy-Platform' = 'kona'
  'X-Fantasy-Source'   = 'kona'
  'x-fantasy-gameId'   = 'ffl'
  'x-fantasy-seasonId' = "$Season"
}

$playersHeaders = @{}
foreach ($k in $commonHeaders.Keys) { $playersHeaders[$k] = $commonHeaders[$k] }
$playersHeaders['X-Fantasy-Filter'] = $filterJson

# Use an explicit cookie container bound to .espn.com
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
try {
  $session.Cookies.Add((New-Object System.Net.Cookie('SWID', $SWID, '/', '.espn.com')))
  $session.Cookies.Add((New-Object System.Net.Cookie('espn_s2', $EspnS2, '/', '.espn.com')))
} catch {
  Write-Warning "Failed to attach cookies to session: $($_.Exception.Message)"
}


# Download JSON with basic error handling
function Invoke-EspnRequest([string]$targetUri, [hashtable]$headersToUse) {
  try {
    # Do not auto-follow redirects; we want to see them and fail fast if sent to HTML/login.
    $r = Invoke-WebRequest -Uri $targetUri -Headers $headersToUse -WebSession $session -MaximumRedirection 0 -ErrorAction Stop
    # If PowerShell autocompletes redirects despite the flag (older versions), capture final URI
    if ($r.BaseResponse -and $r.BaseResponse.ResponseUri -and ($r.BaseResponse.ResponseUri.AbsoluteUri -ne $targetUri)) {
      Write-Warning ("Redirected to: {0}" -f $r.BaseResponse.ResponseUri.AbsoluteUri)
    }
    if ($null -ne $r.StatusCode -and [int]$r.StatusCode -ge 400) {
      Write-Warning ("HTTP {0}: {1} from {2}" -f $r.StatusCode, $r.StatusDescription, $targetUri)
      return $null
    }
    return $r
  } catch {
    $ex = $_.Exception
    $msg = "Request failed for ${targetUri}: $($ex.Message)"
    try {
      $respEx = $ex.Response
      if ($respEx) {
        $status = $null; try { $status = [int]$respEx.StatusCode } catch {}
        $loc = $null;   try { $loc = $respEx.Headers['Location'] } catch {}
        $ctypeEx = $null; try { $ctypeEx = $respEx.ContentType } catch {}
        $bodyText = $null
        try { $sr = New-Object System.IO.StreamReader($respEx.GetResponseStream()); $bodyText = $sr.ReadToEnd(); $sr.Close() } catch {}
        $dbgDir = Join-Path -Path $PSScriptRoot -ChildPath 'data'
        if (-not (Test-Path $dbgDir)) { New-Item -ItemType Directory -Path $dbgDir | Out-Null }
        $ts = (Get-Date -Format 'yyyyMMdd_HHmmss')
        $exHdrPath = Join-Path $dbgDir "espn_exception_headers_${ts}.txt"
        try {
          $hdrDump = @()
          foreach ($hk in $respEx.Headers.AllKeys) { $hdrDump += ("{0}: {1}" -f $hk, ($respEx.Headers[$hk] -join ',')) }
          $hdrDump -join "`r`n" | Set-Content -Path $exHdrPath -Encoding UTF8
        } catch {}
        $exBodyPath = $null
        if ($bodyText) { $exBodyPath = Join-Path $dbgDir "espn_exception_body_${ts}.txt"; [System.IO.File]::WriteAllText($exBodyPath, [string]$bodyText, (New-Object System.Text.UTF8Encoding($false))) }
        $extra = " Status=$status; Location=$loc; Content-Type=$ctypeEx; Headers=$exHdrPath"; if ($exBodyPath) { $extra += "; Body=$exBodyPath" }
        Write-Warning ($msg + $extra)
      } else {
        Write-Warning $msg
      }
    } catch { Write-Warning $msg }
    return $null
  }
}

# Try players endpoint; if it doesn't return JSON, fall back to lm-api leaguedefaults
$resp = Invoke-EspnRequest $uri $playersHeaders
if ($null -eq $resp) { $resp = Invoke-EspnRequest "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/$Season/segments/0/leaguedefaults/1?view=players_wl&view=kona_player_info" $commonHeaders }
if ($null -eq $resp) { $resp = Invoke-EspnRequest "https://fantasy.espn.com/apis/v3/games/ffl/seasons/$Season?view=players_wl&view=kona_player_info" $commonHeaders }
if ($null -eq $resp) { Write-Error "Download failed from all endpoints."; exit 1 }

# Log response headers for debugging
try {
  $dbgDir = Join-Path -Path $PSScriptRoot -ChildPath 'data'
  if (-not (Test-Path $dbgDir)) { New-Item -ItemType Directory -Path $dbgDir | Out-Null }
  $hdrPath = Join-Path $dbgDir ("espn_response_headers_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))
  $resp.Headers | Out-String | Set-Content -Path $hdrPath -Encoding UTF8
} catch { }

# Quick content-type / content sanity check before parsing
$ctype = $resp.Headers['Content-Type']
if ($ctype -and ($ctype -notlike 'application/json*' -and $ctype -notlike 'application/*json*')) {
  try {
    $dbgDir = Join-Path -Path $PSScriptRoot -ChildPath 'data'
    if (-not (Test-Path $dbgDir)) { New-Item -ItemType Directory -Path $dbgDir | Out-Null }
    $bodyPath = Join-Path $dbgDir ("espn_response_body_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))
    [System.IO.File]::WriteAllText($bodyPath, [string]$resp.Content, (New-Object System.Text.UTF8Encoding($false)))
  } catch { }
  $rawPeek = [string]$resp.Content
  if ($rawPeek.Length -gt 300) { $rawPeek = $rawPeek.Substring(0,300) }
  Write-Error "Response is not JSON (Content-Type=$ctype). Saved full body: $bodyPath. Snippet: $rawPeek"; exit 1
}


# Basic sanity check will happen after we capture content.


# Convert JSON -> CSV (season totals only, no calculations beyond selecting ESPN's own appliedTotal)
$raw = $resp.Content
if (-not $raw -or $raw.Trim().Length -eq 0) { Write-Error "Downloaded file is empty."; exit 1 }
if ($raw.TrimStart().Substring(0,1) -notin @('[','{')) {
  $first200 = $raw.Substring(0, [Math]::Min(200, $raw.Length))
  Write-Error "Downloaded content does not look like JSON. First 200 chars: $first200"; exit 1
}

# Write validated raw content to file (UTF-8 without BOM)
[System.IO.File]::WriteAllText($OutJson, $raw, (New-Object System.Text.UTF8Encoding($false)))
try {
  $data = $raw | ConvertFrom-Json -ErrorAction Stop
} catch {
  Write-Error "Failed to parse JSON. First 200 chars: $($raw.Substring(0, [Math]::Min(200, $raw.Length)))"; exit 1
}

# Post-write sanity check of file content shape (array or object with players)
try {
  $first = Get-Content -Path $OutJson -TotalCount 1 -ErrorAction Stop
  if ($first -notmatch '^[\s\[{]') { Write-Warning "Saved file may not be JSON array/object. First bytes: $first" }
} catch {}

# ESPN sometimes wraps players under a root object with a 'players' array
if ($null -ne $data.players) {
  $players = $data.players
} else {
  $players = $data
}
function Get-AppliedTotal([object]$stat) {
  if ($null -eq $stat) { return $null }
  if ($null -ne $stat.appliedTotal) { return [double]$stat.appliedTotal }
  $applied = $stat.appliedStats
  if ($applied -is [hashtable] -or $applied -is [System.Collections.IDictionary]) {
    $sum = 0.0; $has = $false
    foreach ($v in $applied.Values) { if ($v -is [double] -or $v -is [int]) { $sum += [double]$v; $has = $true } }
    if ($has) { return $sum }
  }
  return $null
}

$rows = foreach ($p in $players) {
  if (-not $p.stats) { continue }
  # 1) Season projections (preferred): 0|0|1 or 0|2|1
  $seasonProj = $p.stats | Where-Object { $_.scoringPeriodId -eq 0 -and ($_.statSplitTypeId -eq 0 -or $_.statSplitTypeId -eq 2) -and $_.statSourceId -eq 1 } | Select-Object -First 1
  $pts = Get-AppliedTotal $seasonProj
  # 2) Sum weekly projections if season aggregate missing
  if ($null -eq $pts) {
    $weekly = $p.stats | Where-Object { $_.statSplitTypeId -eq 1 -and $_.statSourceId -eq 1 -and $_.scoringPeriodId -ge 1 }
    if ($weekly) {
      $sum = 0.0; $has = $false
      foreach ($w in $weekly) { $wt = Get-AppliedTotal $w; if ($wt -ne $null) { $sum += $wt; $has = $true } }
      if ($has) { $pts = $sum }
    }
  }
  # 3) Fallback to season actuals 0|0|0 or 0|2|0 if still null
  if ($null -eq $pts) {
    $seasonActual = $p.stats | Where-Object { $_.scoringPeriodId -eq 0 -and ($_.statSplitTypeId -eq 0 -or $_.statSplitTypeId -eq 2) -and $_.statSourceId -eq 0 } | Select-Object -First 1
    $pts = Get-AppliedTotal $seasonActual
  }
  # 4) Fallback to sum weekly actuals if still null
  if ($null -eq $pts) {
    $weeklyAct = $p.stats | Where-Object { $_.statSplitTypeId -eq 1 -and $_.statSourceId -eq 0 -and $_.scoringPeriodId -ge 1 }
    if ($weeklyAct) {
      $sum = 0.0; $has = $false
      foreach ($w in $weeklyAct) { $wt = Get-AppliedTotal $w; if ($wt -ne $null) { $sum += $wt; $has = $true } }
      if ($has) { $pts = $sum }
    }
  }
  [PSCustomObject]@{
    player_id   = $p.id
    name        = $p.fullName
    position_id = $p.defaultPositionId
    team_id     = $p.proTeamId
    season      = $Season
    proj_points = $pts
  }
}
$rows | Export-Csv -Path $OutCsv -NoTypeInformation -Encoding UTF8


Write-Host "Saved:`n JSON -> $OutJson`n CSV -> $OutCsv"
