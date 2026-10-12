param(
  [Parameter(Mandatory=$true)][string]$InputFile,
  [Parameter(Mandatory=$true)][string]$Participants,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [string]$Transcript = "",
  [string]$Video = "",
  [string]$Title = "Biên bản cuộc họp",
  [string]$MeetingDate = ""
)

$ErrorActionPreference = "Stop"
$skillDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$python = if (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { "python" }
$arguments = @(
  (Join-Path $skillDir "scripts\meeting_agent.py"),
  "--input", $InputFile,
  "--participants", $Participants,
  "--output", $OutputDir,
  "--title", $Title,
  "--meeting-date", $MeetingDate
)
if ($Transcript) { $arguments += @("--transcript", $Transcript) }
if ($Video) { $arguments += @("--video", $Video) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
