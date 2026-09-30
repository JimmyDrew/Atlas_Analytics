$ErrorActionPreference = 'Stop'
$raw = Join-Path $PSScriptRoot 'data/raw'
New-Item -ItemType Directory -Force -Path $raw | Out-Null
$sources = @{
    retail = 'https://archive.ics.uci.edu/static/public/352/online+retail.zip'
    bike = 'https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip'
    energy = 'https://archive.ics.uci.edu/static/public/374/appliances+energy+prediction.zip'
}
foreach ($name in $sources.Keys) {
    $target = Join-Path $raw ($name + '.zip')
    if (-not (Test-Path -LiteralPath $target)) {
        Invoke-WebRequest -Uri $sources[$name] -OutFile $target
    }
}
Write-Host 'Archives downloaded. Now run python pipeline.py --download to extract and analyze.'
