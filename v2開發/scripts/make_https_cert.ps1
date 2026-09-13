param([string]$LanIp = "192.168.0.22")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$httpsDir = Join-Path $root ".local\https"
New-Item -ItemType Directory -Force -Path $httpsDir | Out-Null
$rootSubject = "CN=Foodiemo Local Demo Root CA"
$rootCert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $rootSubject -and $_.NotAfter -gt (Get-Date).AddDays(30) } | Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $rootCert) { $rootCert = New-SelfSignedCertificate -Type Custom -Subject $rootSubject -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -KeyExportPolicy Exportable -KeyUsage CertSign,CRLSign,DigitalSignature -TextExtension @("2.5.29.19={critical}{text}CA=true&pathlength=1") -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(2) }
$leafSubject = "CN=$LanIp"
$leaf = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $leafSubject -and $_.NotAfter -gt (Get-Date).AddDays(30) } | Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $leaf) { $leaf = New-SelfSignedCertificate -Type Custom -Subject $leafSubject -Signer $rootCert -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -KeyExportPolicy Exportable -KeyUsage DigitalSignature,KeyEncipherment -TextExtension @("2.5.29.17={text}IPAddress=$LanIp&DNS=localhost") -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddMonths(6) }
$rootCer = Join-Path $httpsDir "foodiemo-local-root.cer"
$leafPfx = Join-Path $httpsDir "foodiemo-local-server.pfx"
$certPem = Join-Path $httpsDir "foodiemo-local-server-cert.pem"
$keyPem = Join-Path $httpsDir "foodiemo-local-server-key.pem"
Export-Certificate -Cert $rootCert -FilePath $rootCer -Force | Out-Null
$passwordText = [Guid]::NewGuid().ToString();$password = ConvertTo-SecureString $passwordText -AsPlainText -Force
Export-PfxCertificate -Cert $leaf -FilePath $leafPfx -Password $password -Force | Out-Null
$converter = Join-Path $httpsDir "_convert_pfx.py"
$python = @"
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
pfx = Path(sys.argv[1]); cert_out = Path(sys.argv[2]); key_out = Path(sys.argv[3]); password = sys.argv[4].encode()
key, cert, _ = pkcs12.load_key_and_certificates(pfx.read_bytes(), password)
if key is None or cert is None: raise SystemExit("PFX did not contain key and certificate")
cert_out.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
key_out.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
"@
[IO.File]::WriteAllText($converter, $python, [Text.UTF8Encoding]::new($false))
try { & (Join-Path $root ".venv\Scripts\python.exe") $converter $leafPfx $certPem $keyPem $passwordText } finally { Remove-Item -LiteralPath $converter,$leafPfx -Force -ErrorAction SilentlyContinue }
try { Import-Certificate -FilePath $rootCer -CertStoreLocation Cert:\CurrentUser\Root | Out-Null } catch {}
Write-Output "HTTPS certificate files created under $httpsDir"
Write-Output "Install this file on the iPhone: $rootCer"