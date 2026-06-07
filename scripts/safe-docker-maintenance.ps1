param(
    [int]$UnusedHours = 168,
    [switch]$StopOptional,
    [switch]$PruneBuildCacheAll
)

$ErrorActionPreference = "Stop"

$optionalContainers = @(
    "aegis-grafana",
    "aegis-postgres-exporter",
    "aegis-redis-exporter",
    "aegis-pushgateway",
    "aegis-metrics-pusher",
    "aegis-optimizer",
    "aegis-macro-bridge"
)

$healthUrls = @(
    "http://localhost:8502/health",
    "http://localhost:8001/health",
    "http://localhost:3001"
)

function Test-Endpoint {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
            throw "Unexpected HTTP status $($response.StatusCode)"
        }
        Write-Host "OK  $Url" -ForegroundColor Green
    }
    catch {
        Write-Host "ERR $Url - $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

Write-Host "Docker usage before cleanup" -ForegroundColor Cyan
docker system df

Write-Host "Pruning stopped containers, unused networks, and unused images older than $UnusedHours hours..." -ForegroundColor Cyan
docker container prune --force --filter "until=${UnusedHours}h"
docker network prune --force --filter "until=${UnusedHours}h"
docker image prune --all --force --filter "until=${UnusedHours}h"

if ($PruneBuildCacheAll) {
    Write-Host "Pruning all Docker build cache. Running containers and volumes are not touched." -ForegroundColor Cyan
    docker builder prune --all --force
}
else {
    Write-Host "Pruning Docker build cache older than $UnusedHours hours..." -ForegroundColor Cyan
    docker builder prune --all --force --filter "until=${UnusedHours}h"
}

if ($StopOptional) {
    Write-Host "Stopping optional non-core containers..." -ForegroundColor Cyan
    foreach ($container in $optionalContainers) {
        $exists = docker ps --format "{{.Names}}" | Where-Object { $_ -eq $container }
        if ($exists) {
            docker stop $container
        }
    }
}

Write-Host "Verifying core endpoints..." -ForegroundColor Cyan
foreach ($url in $healthUrls) {
    Test-Endpoint -Url $url
}

Write-Host "Docker usage after cleanup" -ForegroundColor Cyan
docker system df

Write-Host "Done. Volumes were not pruned." -ForegroundColor Green
