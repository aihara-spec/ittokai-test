$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt | Out-Host
if (!(Test-Path "$PSScriptRoot\tools")) { New-Item -ItemType Directory "$PSScriptRoot\tools" | Out-Null }
$cf = "$PSScriptRoot\tools\cloudflared.exe"
if (!(Test-Path $cf)) {
  Write-Host "Downloading Cloudflare tunnel tool..."
  Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf
}
$server = Start-Process -FilePath "python" -ArgumentList "server.py" -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 2
$log = "$PSScriptRoot\cloudflared.log"
if (Test-Path $log) { Remove-Item $log -Force }
$tunnel = Start-Process -FilePath $cf -ArgumentList @("tunnel","--url","http://127.0.0.1:8000","--no-autoupdate") -RedirectStandardError $log -RedirectStandardOutput $log -PassThru -WindowStyle Minimized
$url = $null
for ($i=0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  if (Test-Path $log) {
    $m = Select-String -Path $log -Pattern 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' -AllMatches
    if ($m) { $url = $m.Matches[0].Value; break }
  }
}
if ($url) {
  Set-Content -Path "$PSScriptRoot\PUBLIC_URL.txt" -Value $url -Encoding UTF8
  Set-Clipboard -Value $url
  Write-Host ""
  Write-Host "PUBLIC URL: $url" -ForegroundColor Green
  Write-Host "The URL was copied to the clipboard and saved in PUBLIC_URL.txt."
  Start-Process $url
} else {
  Write-Host "Could not get a public URL. Please send cloudflared.log to support." -ForegroundColor Red
}
Write-Host ""
Write-Host "Keep this window open while using ITTOKAI."
Write-Host "Press Enter to stop."
Read-Host | Out-Null
try { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue } catch {}
try { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue } catch {}
