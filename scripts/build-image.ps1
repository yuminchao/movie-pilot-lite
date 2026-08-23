[CmdletBinding()]
param(
    [string]$Tag = "movie-pilot-lite:latest",
    [string]$Platform = "",
    [switch]$Push,
    [switch]$NoCache,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    @"
Usage:
  .\scripts\build-image.ps1 [-Tag <name:tag>] [-Platform <platform>] [-Push] [-NoCache]

Examples:
  .\scripts\build-image.ps1
  .\scripts\build-image.ps1 -Tag ghcr.io/example/movie-pilot-lite:0.1.0
  .\scripts\build-image.ps1 -Platform linux/amd64 -Push
"@
    exit 0
}

if ($Platform -match "," -and -not $Push) {
    throw "Multi-platform builds require -Push because Docker cannot --load a multi-platform image."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker command not found. Install Docker Desktop or Docker Engine first."
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dockerfile = Join-Path $projectRoot "Dockerfile"
if (-not (Test-Path -LiteralPath $dockerfile)) {
    throw "Dockerfile not found at: $dockerfile"
}

$arguments = @("buildx", "build", "--file", $dockerfile, "--tag", $Tag)
if ($Platform) { $arguments += @("--platform", $Platform) }
if ($NoCache) { $arguments += "--no-cache" }
if ($Push) { $arguments += "--push" } else { $arguments += "--load" }
$arguments += $projectRoot

Write-Host "Building image: $Tag"
if ($Platform) { Write-Host "Platform: $Platform" }
if ($Push) { Write-Host "Push enabled" }

& docker @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Docker image build failed with exit code: $LASTEXITCODE"
}

Write-Host "Image build complete: $Tag"
