$ErrorActionPreference = "Stop"

$emailVariable = "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL"
$passwordVariable = "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD"

Write-Host "Configuração local do Ultrapack para o CrapScraper."
Write-Host "Os valores serão salvos somente no ambiente User do Windows."

$email = Read-Host "E-mail Ultrapack"
if ([string]::IsNullOrWhiteSpace($email)) {
    throw "$emailVariable não pode ficar vazia."
}

$securePassword = Read-Host "Senha Ultrapack" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}

if ([string]::IsNullOrWhiteSpace($password)) {
    throw "$passwordVariable não pode ficar vazia. Nenhuma credencial foi salva."
}

[Environment]::SetEnvironmentVariable($emailVariable, $email.Trim(), "User")
[Environment]::SetEnvironmentVariable($passwordVariable, $password, "User")
$email = $null
$password = $null

Write-Host "Credenciais Ultrapack salvas. Reinicie o CrapScraper pelo autoscraper.bat."
