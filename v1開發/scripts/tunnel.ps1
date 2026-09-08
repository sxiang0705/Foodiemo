param(
    [string]$SshHost,
    [string]$SshUser,
    [int]$SshPort = 22,
    [int]$LocalPort = 55432
)
$ErrorActionPreference = 'Stop'
if (-not $SshHost -or -not $SshUser) {
    throw 'Specify -SshHost and -SshUser; enter password only at the SSH prompt.'
}
if ($SshHost.StartsWith('-') -or $SshUser.StartsWith('-') -or $LocalPort -lt 1024 -or $LocalPort -gt 65535 -or $SshPort -lt 1 -or $SshPort -gt 65535) {
    throw 'Invalid SSH target or port'
}
Set-Location $PSScriptRoot/..
New-Item -ItemType Directory -Force -Path .local | Out-Null
& ssh -N -L "127.0.0.1:${LocalPort}:127.0.0.1:5432" -p $SshPort -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=.local/known_hosts "$SshUser@$SshHost"
exit $LASTEXITCODE
