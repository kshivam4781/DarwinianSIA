# Load .env into the current PowerShell session (does not print secrets).
# ICML Thesis 1 (Tick 289/308–311): Nebius-first. Anthropic is optional under
# default kimi-nebius-pydantic-meta; HF_TOKEN needed for --fetch-diamond unless
# a local gpqa_diamond.csv is present (see docs/ICML_HUMAN_UNBLOCK.md).
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

Write-Host "Loaded keys from .env (ICML: Nebius required; Anthropic optional; HF or CSV for diamond):"
if ($env:NEBIUS_API_KEY) {
    Write-Host "  NEBIUS_API_KEY: SET (required for ICML live)"
} else {
    Write-Host "  NEBIUS_API_KEY: missing (required for ICML live G2→G4)"
}
$hfPresent = $env:HF_TOKEN -or $env:HUGGINGFACE_HUB_TOKEN
if ($hfPresent) {
    Write-Host "  HF_TOKEN / HUGGINGFACE_HUB_TOKEN: SET (for --fetch-diamond)"
} else {
    Write-Host "  HF_TOKEN: missing (optional if local gpqa_diamond.csv is present)"
}
if ($env:ANTHROPIC_API_KEY) {
    Write-Host "  ANTHROPIC_API_KEY: SET (optional under Nebius meta)"
} else {
    Write-Host "  ANTHROPIC_API_KEY: absent (optional — only needed if ICML_META_AGENT_PROFILE=default-meta)"
}
if ($env:TAVILY_API_KEY) {
    Write-Host "  TAVILY_API_KEY: SET"
} else {
    Write-Host "  TAVILY_API_KEY: absent (optional)"
}
