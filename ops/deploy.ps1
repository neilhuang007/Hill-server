# One command from a clean, committed main checkout. Secrets stay on the server.
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('Microsoft', 'Development')]
    [string]$Mode,
    [string]$PrivateKey = 'C:/Users/neil_/.ssh/hetzner.ppk'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    [void](Get-Command git -ErrorAction Stop)
    [void](Get-Command plink.exe -ErrorAction Stop)
    if (-not (Test-Path -LiteralPath $PrivateKey -PathType Leaf)) { throw 'PuTTY private key not found.' }
    $branch = Invoke-Checked git @('branch', '--show-current')
    if ($branch -ne 'main') { throw 'Deploy from main after reviewing and committing the changes.' }
    $dirty = Invoke-Checked git @('status', '--porcelain')
    if ($dirty) { throw 'Commit or preserve local changes before deployment; the checkout must be clean.' }
    $origin = Invoke-Checked git @('remote', 'get-url', 'origin')
    if ($origin -notin @('https://github.com/neilhuang007/Hill-server.git', 'git@github.com:neilhuang007/Hill-server.git')) {
        throw 'Origin must be the Hill-server GitHub repository.'
    }
    $revision = Invoke-Checked git @('rev-parse', 'HEAD')
    if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Cannot identify the committed revision.' }
    $installMode = if ($Mode -eq 'Microsoft') { '--microsoft' } else { '--allow-development-auth' }
    Invoke-Checked git @('push', 'origin', 'HEAD:refs/heads/main')
    # Only a validated SHA and fixed option are interpolated into the remote shell.
    # Hold one host lock across pull/build/install; no reset, force-push or source copy.
    $remoteScript = @'
set -euo pipefail
exec 8>/run/lock/hill175-deploy.lock
flock -n 8 || { echo 'Another Hill deployment is running.' >&2; exit 1; }
cd /opt/Hill-server
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
case "$(git remote get-url origin)" in
  https://github.com/neilhuang007/Hill-server.git|git@github.com:neilhuang007/Hill-server.git) ;;
  *) echo 'Unexpected deployment Git origin.' >&2; exit 1 ;;
esac
git pull --ff-only origin main
test "$(git rev-parse HEAD)" = __REVISION__ || { echo 'GitHub main changed; rerun from the reviewed current revision.' >&2; exit 1; }
log="/opt/hill175-deploy-$(date -u +%Y%m%dT%H%M%SZ).log"
umask 077
bash ops/install-server.sh __MODE__ 2>&1 | tee "$log"
echo "Deployment log: $log"
'@
    $remoteScript = $remoteScript.Replace('__REVISION__', $revision).Replace('__MODE__', $installMode)
    $commandFile = [System.IO.Path]::GetTempFileName()
    try {
        # plink -m sends the fixed command over SSH; no credentials are written here.
        $quote = [string][char]39
        $escapedQuote = $quote + [char]34 + $quote + [char]34 + $quote
        $command = 'bash -lc ' + $quote + $remoteScript.Replace($quote, $escapedQuote).Replace("`r`n", "`n") + $quote
        [System.IO.File]::WriteAllText($commandFile, $command, [System.Text.UTF8Encoding]::new($false))
        Invoke-Checked plink.exe @('-batch', '-i', $PrivateKey, 'root@135.181.78.188', '-m', $commandFile)
    }
    finally { Remove-Item -LiteralPath $commandFile -ErrorAction SilentlyContinue }
}
finally { Pop-Location }
