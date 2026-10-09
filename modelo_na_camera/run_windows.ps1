param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Arguments
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'modelo_visao_computacional\.venv\Scripts\python.exe'
$script = Join-Path $PSScriptRoot 'main.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual não encontrado em $python. Crie-o conforme modelo_visao_computacional/README.md."
}

& $python $script @Arguments
exit $LASTEXITCODE
