param(
    [string]$PythonPath = '',
    [switch]$IncludeBrowser
)
$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) { $PythonPath = Join-Path $workspacePath 'backend/.venv-audit/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Provide -PythonPath pointing to an environment installed from backend/requirements-audit.txt.' }
$checks = @(
    @{Name='frontend-typecheck'; Directory='frontend'; Command='npm.cmd'; Arguments=@('run','type-check')},
    @{Name='frontend-build'; Directory='frontend'; Command='npm.cmd'; Arguments=@('run','build')},
    @{Name='frontend-lint'; Directory='frontend'; Command='npm.cmd'; Arguments=@('run','lint')},
    @{Name='backend-tests'; Directory='backend'; Command=$PythonPath; Arguments=@('-m','pytest','-q','--tb=short','--junitxml=audit-results.xml')},
    @{Name='referral-service-tests'; Directory='services'; Command='npm.cmd'; Arguments=@('test','--','--runInBand')},
    @{Name='payroll-adapter-tests'; Directory='payroll'; Command='npm.cmd'; Arguments=@('test','--','--runInBand')}
)
if ($IncludeBrowser) {
    $checks += @{Name='browser-smoke'; Directory='frontend'; Command='npm.cmd'; Arguments=@('run','test:smoke')}
}
$results = @()
foreach ($check in $checks) {
    Push-Location (Join-Path $workspacePath $check.Directory)
    try {
        $checkArguments = $check.Arguments
        & $check.Command @checkArguments
        $results += [pscustomobject]@{Check=$check.Name; ExitCode=$LASTEXITCODE}
    } finally { Pop-Location }
}
$results | Format-Table
if ($results.Where({$_.ExitCode -ne 0}).Count) { exit 1 }
