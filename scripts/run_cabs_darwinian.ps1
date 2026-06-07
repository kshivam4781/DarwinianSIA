# CABS + Darwinian two-step merge pipeline (Section 20.6)
# Usage: .\scripts\run_cabs_darwinian.ps1 -RunId 400 -MaxGen 3

param(
    [int]$RunId = 400,
    [int]$MaxGen = 3,
    [int]$PopulationSize = 2,
    [int]$EliteCount = 1,
    [int]$EvalSubset = 15,
    [string]$SiaRoot = "c:\Users\MSPSA\Documents\SIA",
    [string]$Sia2Root = "c:\Users\MSPSA\Documents\SIA2"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Step 1: Darwinian gen 1 ===" -ForegroundColor Cyan
Push-Location $SiaRoot
sia run --task gpqa --darwinian --population_size $PopulationSize --elite_count $EliteCount `
    --max_gen 1 --run_id $RunId --eval_subset $EvalSubset --baseline_seed --no-web --seed 42
Pop-Location

Write-Host "=== Step 2: CABS analyze + committee on gen 1 ===" -ForegroundColor Cyan
Push-Location $Sia2Root
.\.venv\Scripts\Activate.ps1
$runDir = Join-Path $SiaRoot "runs\run_$RunId"
sia-cabs-tools analyze --run-dir $runDir --max-gen 1
sia-cabs-tools committee --run-dir $runDir --generation 1 --offline --task-hint gpqa
Pop-Location

Write-Host "=== Step 3: Darwinian gen 2+ with --cabs ===" -ForegroundColor Cyan
Push-Location $SiaRoot
sia run --task gpqa --darwinian --resume --cabs --max_gen $MaxGen --run_id $RunId `
    --population_size $PopulationSize --elite_count $EliteCount --eval_subset $EvalSubset --no-web
Pop-Location

Write-Host "=== Done. Inspect: $runDir/belief_store/ ===" -ForegroundColor Green
