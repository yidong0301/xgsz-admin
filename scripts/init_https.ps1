# 芯光数智 · 域名 + HTTPS 初始化（Windows PowerShell 5.1+）
# 用法：
#   .\scripts\init_https.ps1 -Domain ops.example.com -Email ops@example.com
#   .\scripts\init_https.ps1 -Domain local.test -SelfSigned
#   .\scripts\init_https.ps1 -Domain ops.example.com -Email ops@example.com -Staging
param(
  [Parameter(Mandatory = $true)][string]$Domain,
  [string]$Email = "",
  [switch]$SelfSigned,
  [switch]$Staging
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path 'docker-compose.prod.yml')) { throw '请在项目根目录执行本脚本（找不到 docker-compose.prod.yml）' }
New-Item -ItemType Directory -Force -Path 'nginx\certs', 'nginx\www' | Out-Null

$python = 'python'
if (Test-Path 'venv\Scripts\python.exe') { $python = 'venv\Scripts\python.exe' }

if ($SelfSigned) {
  & $python tools\gen_self_signed_cert.py --domain $Domain
} else {
  if (-not $Email) { throw "申请 Let's Encrypt 证书需要邮箱：-Email ops@example.com" }
  Write-Host ">>> 使用 certbot standalone 申请证书（需要 80 端口空闲）"
  $dockerArgs = @(
    'run', '--rm', '-p', '80:80',
    '-v', "${PWD}\nginx\certs:/etc/letsencrypt",
    '-v', "${PWD}\nginx\www:/var/www/certbot",
    'certbot/certbot', 'certonly', '--standalone',
    '-d', $Domain, '--email', $Email, '--agree-tos', '--no-eff-email'
  )
  if ($Staging) { $dockerArgs += '--staging' }
  & docker @dockerArgs
}

$env:DOMAIN = $Domain
if (-not $env:HTTP_PORT) { $env:HTTP_PORT = '80' }
if (-not $env:HTTPS_PORT) { $env:HTTPS_PORT = '443' }
Write-Host ">>> 启动生产栈（域名：$Domain）"
docker compose -f docker-compose.prod.yml up -d

Write-Host ""
Write-Host "完成。访问：https://$Domain"
Write-Host "证书续期：docker compose -f docker-compose.prod.yml --profile certbot up -d certbot"
