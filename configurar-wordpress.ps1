$ErrorActionPreference = "Stop"

$variables = @(
    @{ Name = "SCRAPER_WP_BASE_URL"; Label = "URL base WordPress"; Secret = $false },
    @{ Name = "SCRAPER_WP_USERNAME"; Label = "Usuário WordPress"; Secret = $false },
    @{ Name = "SCRAPER_WP_APPLICATION_PASSWORD"; Label = "Application Password WordPress"; Secret = $true },
    @{ Name = "SCRAPER_WC_CONSUMER_KEY"; Label = "Consumer Key WooCommerce"; Secret = $true },
    @{ Name = "SCRAPER_WC_CONSUMER_SECRET"; Label = "Consumer Secret WooCommerce"; Secret = $true }
)

Write-Host "Configuração local do CrapScraper (ambiente User do Windows)."
Write-Host "Nenhum valor será exibido ou gravado no projeto."

foreach ($item in $variables) {
    if ($item.Secret) {
        $secure = Read-Host $item.Label -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
    else {
        $value = Read-Host $item.Label
    }

    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$($item.Name) não pode ficar vazia. Nenhuma configuração posterior foi aplicada."
    }
    [Environment]::SetEnvironmentVariable($item.Name, $value.Trim(), "User")
    $value = $null
}

Write-Host "Configuração salva. Feche e abra novamente o CrapScraper pelo autoscraper.bat."
