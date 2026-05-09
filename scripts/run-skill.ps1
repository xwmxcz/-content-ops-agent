param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('contract', 'frontend', 'release')]
  [string]$Mode,

  [string[]]$Changed,
  [string]$Name,
  [string]$Route,
  [string]$RouteName,
  [switch]$WithApi,
  [switch]$WithStore,
  [switch]$Run,
  [switch]$Force,
  [switch]$SkipFrontend,
  [switch]$ContinueOnError,
  [string]$PythonExe = 'F:\miniconda\envs\only\python.exe'
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$ContractScript = '.codex\skills\api-contract-guard\scripts\contract_guard.py'
$FrontendScript = '.codex\skills\frontend-page-pattern\scripts\scaffold_page.py'
$ReleaseScript = '.codex\skills\release-sanity-check\scripts\run_sanity.py'

if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw "Python executable not found: $PythonExe"
}

switch ($Mode) {
  'contract' {
    $args = @($ContractScript)
    if ($Changed -and $Changed.Count -gt 0) {
      $args += '--changed'
      $args += $Changed
    }
    if ($Run) {
      $args += '--run'
    }
    & $PythonExe @args
    break
  }

  'frontend' {
    if (-not $Name) {
      throw 'frontend mode requires --Name'
    }

    $args = @($FrontendScript, '--name', $Name)
    if ($Route) {
      $args += @('--route', $Route)
    }
    if ($RouteName) {
      $args += @('--route-name', $RouteName)
    }
    if ($WithApi) {
      $args += '--with-api'
    }
    if ($WithStore) {
      $args += '--with-store'
    }
    if ($Force) {
      $args += '--force'
    }

    & $PythonExe @args
    break
  }

  'release' {
    $args = @($ReleaseScript, '--python', $PythonExe)
    if ($SkipFrontend) {
      $args += '--skip-frontend'
    }
    if ($ContinueOnError) {
      $args += '--continue-on-error'
    }

    & $PythonExe @args
    break
  }
}