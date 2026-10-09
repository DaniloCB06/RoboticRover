<#!
.SYNOPSIS
    Inicia o treinamento completo do detector de peças.

.EXAMPLE
    .\modelo_visao_computacional\treinar.ps1
#>

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$main = Join-Path $projectRoot 'main.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente Python não encontrado em $python. Instale as dependências antes de treinar."
}

& $python $main @args
exit $LASTEXITCODE
