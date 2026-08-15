$ErrorActionPreference = "Stop"

Write-Host "Configuracao central do CrapScraper (Environment User do Windows)."
Write-Host "[1] WordPress/WooCommerce"
Write-Host "[2] Ultrapack"
Write-Host "[3] SSH"
Write-Host "[4] Tudo"
Write-Host "[5] Execucao de atualizacoes"
Write-Host "[6] PluginTheme"
$choice = Read-Host "Escolha um grupo"
if ($choice -notin @("1", "2", "3", "4", "5", "6")) { throw "Opcao invalida." }

$metadataJson = & python -c "import json; from app.configuration import ENVIRONMENT_VARIABLES; print(json.dumps([{'name': x.name, 'group': x.group, 'secret': x.secret, 'required': bool(x.required_for)} for x in ENVIRONMENT_VARIABLES]))"
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel ler o inventario central de configuracao." }
$metadata = $metadataJson | ConvertFrom-Json
$groups = switch ($choice) {
    "1" { @("wordpress", "woocommerce") }
    "2" { @("ultrapack") }
    "3" { @("ssh") }
    "4" { @("wordpress", "woocommerce", "ultrapack", "plugintheme", "ssh") }
    "5" { @("update_execution") }
    "6" { @("plugintheme") }
}
$selected = @($metadata | Where-Object { ($_.required -or $_.group -eq "update_execution") -and $_.group -in $groups })

if ($choice -eq "5") {
    Write-Warning "Esta opcao habilita alteracoes reais no servidor e WooCommerce."
    Write-Host "O default seguro e false. Digite true somente durante homologacao consciente."
}

foreach ($item in $selected) {
    $existing = [Environment]::GetEnvironmentVariable($item.name, "User")
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        $replace = Read-Host "$($item.name) ja esta PRESENTE. Substituir? [s/N]"
        if ($replace -notmatch '^[sS]$') { continue }
    }
    if ($item.secret) {
        $secure = Read-Host $item.name -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    } else { $value = Read-Host $item.name }
    if ([string]::IsNullOrWhiteSpace($value)) { continue }
    [Environment]::SetEnvironmentVariable($item.name, $value.Trim(), "User")
    $value = $null
}

Write-Host "Status final:"
foreach ($item in $selected) {
    $configured = [Environment]::GetEnvironmentVariable($item.name, "User")
    $status = if ([string]::IsNullOrWhiteSpace($configured)) { "AUSENTE" } else { "PRESENTE" }
    Write-Host "$($item.name) = $status"
}
Write-Host "Reinicie o CrapScraper para carregar as alteracoes."
