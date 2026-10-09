<#!
.SYNOPSIS
    Gera imagens lado a lado para as 33 imagens do conjunto de teste.

.EXAMPLE
    .\modelo_visao_computacional\ver_teste_visual.ps1
#>

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$script = Join-Path $projectRoot 'scripts\visualize_test.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente Python não encontrado em $python."
}

& $python $script @args
exit $LASTEXITCODE
