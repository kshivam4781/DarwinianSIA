# Load .env into the current PowerShell session (does not print secrets).
$envFile = Join-Path $PSScriptRoot ".." ".env" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $envFile) {
    Write-Host "No .env file found. Copy .env.example to .env and add your keys."
    exit 1
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Count -eq 2) {
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name -and $value) {
            Set-Item -Path "env:$name" -Value $value
        }
    }
}

Write-Host "Loaded keys from .env:"
if ($env:ANTHROPIC_API_KEY) { Write-Host "  ANTHROPIC_API_KEY: SET" } else { Write-Host "  ANTHROPIC_API_KEY: missing" }
if ($env:NEBIUS_API_KEY)       { Write-Host "  NEBIUS_API_KEY: SET" }       else { Write-Host "  NEBIUS_API_KEY: missing" }
