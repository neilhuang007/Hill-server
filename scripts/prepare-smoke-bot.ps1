$ErrorActionPreference = 'Stop'

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BotRoot = Join-Path $RepositoryRoot 'runtime\smoke-bot\mineflayer'
$MineflayerRepository = 'https://github.com/zkonikishi/Mineflayer.git'
$MineflayerCommit = '636d4b6f3f6f20c4d29ed9dbb3a9d462fa6c7aa2'

if (-not (Test-Path -LiteralPath $BotRoot)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BotRoot) | Out-Null
    & git clone $MineflayerRepository $BotRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to clone the Minecraft 26.2 Mineflayer compatibility fork.'
    }
}

$ResolvedBotRoot = (Resolve-Path -LiteralPath $BotRoot).Path
$Remote = (& git -C $ResolvedBotRoot remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $Remote -notmatch 'zkonikishi[/\\]Mineflayer(?:\.git)?$') {
    throw "Unexpected smoke-bot repository at $ResolvedBotRoot ($Remote)."
}

& git -C $ResolvedBotRoot fetch origin $MineflayerCommit
if ($LASTEXITCODE -ne 0) {
    throw "Unable to fetch pinned Mineflayer commit $MineflayerCommit."
}
& git -C $ResolvedBotRoot checkout --detach $MineflayerCommit
if ($LASTEXITCODE -ne 0) {
    throw "Unable to check out pinned Mineflayer commit $MineflayerCommit."
}

& node (Join-Path $PSScriptRoot 'patch-smoke-bot-protocol.mjs') $ResolvedBotRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to apply the pinned Minecraft 26.2 protocol-data correction.'
}

# Use the compatibility fork's patched top-level data package everywhere. This
# prevents Yarn from nesting a newer unpatched minecraft-data release.
Push-Location $ResolvedBotRoot
try {
    & npm pkg set 'resolutions.minecraft-data=3.113.0'
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to pin the smoke-bot minecraft-data resolution.'
    }
} finally {
    Pop-Location
}

Push-Location $ResolvedBotRoot
try {
    & yarn install --production --ignore-optional --non-interactive
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to install smoke-bot dependencies with Yarn.'
    }
} finally {
    Pop-Location
}

Push-Location $ResolvedBotRoot
try {
    & node -e "const data=require('minecraft-data')('26.2'); const registry=require('prismarine-registry')('26.2'); if (!data?.protocol || data.version.version !== 776 || !registry) process.exit(1); console.log('Minecraft 26.2 smoke-bot dependencies are ready.')"
    if ($LASTEXITCODE -ne 0) {
        throw 'The installed smoke-bot dependencies do not support Minecraft 26.2 protocol 776.'
    }
} finally {
    Pop-Location
}

Write-Host "Run the player smoke test with: node scripts/smoke-player.mjs"
