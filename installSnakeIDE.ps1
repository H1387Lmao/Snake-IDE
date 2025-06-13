# Auto-elevate if not admin
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Host "Restarting script with admin rights..."
    Start-Process powershell "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Set working directory to script location
$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# Ensure secure TLS
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Get latest release from GitHub
$repoApi = "https://api.github.com/repos/H1387Lmao/Snake-IDE/releases/latest"
$headers = @{ "User-Agent" = "PowerShell" }
$release = Invoke-RestMethod -Uri $repoApi -Headers $headers

# Find non-source .zip
$asset = $release.assets | Where-Object { $_.name -like "*.zip" -and $_.name -notlike "*source*" } | Select-Object -First 1
if (-not $asset) {
    Write-Error "No suitable zip asset found."
    exit 1
}

# Prepare zip path
$zipPath = Join-Path $scriptDir $asset.name

# Check if file exists
if (Test-Path $zipPath) {
    $bytes = (Get-Item $zipPath).Length
    $kb = [Math]::Round($bytes / 1KB, 2)
    $mb = [Math]::Round($bytes / 1MB, 2)
    Write-Host "`n[OK] Using existing $($asset.name): $kb KB ($mb MB)"
} else {
    # Get size from GitHub metadata
    $bytes = $asset.size
    $kb = [Math]::Round($bytes / 1KB, 2)
    $mb = [Math]::Round($bytes / 1MB, 2)
    Write-Host "⬇️ Downloading $($asset.name): $kb KB ($mb MB)..."
    
    # Download zip
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
}

# Locate snakeide.exe
$exePath = Get-ChildItem -Path $scriptDir -Recurse -Filter "snakeide.exe" | Select-Object -First 1
if (-not $exePath) {
    Write-Error "snakeide.exe not found after extraction."
    exit 1
}

# Registry paths
$menuPath = "Registry::HKEY_CLASSES_ROOT\Directory\Background\shell\Open In SnakeIDE"
$commandPath = "$menuPath\command"

# Remove old menu if it exists
if (Test-Path $menuPath) {
    Remove-Item -Path $menuPath -Recurse -Force
}

# Create new context menu
New-Item -Path $commandPath -Force | Out-Null
Set-ItemProperty -Path $commandPath -Name "(default)" -Value "`"$($exePath.FullName)`" `"%V`""

Write-Host "`n[OK] Snake-IDE installed and context menu added successfully."
Read-Host "Press enter to exit..."