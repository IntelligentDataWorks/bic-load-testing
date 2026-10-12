<#
.SYNOPSIS
    Mints a Databricks OAuth U2M access token for the app's workspace and
    exports it as BIC_AUTH_TOKEN for the current shell session only.

.DESCRIPTION
    Replaces reading a static PAT out of .databrickscfg. `databricks auth login`
    opens a browser once per workspace and caches a refresh token locally (via
    the Databricks CLI, not this repo); `databricks auth token` then returns a
    short-lived access token, refreshing silently if needed. The token is never
    written to disk here -- only exported into the current process environment.

.EXAMPLE
    .\scripts\get-databricks-token.ps1 -WorkspaceHost https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com
    locust --config config/locust.deployed-smoke.conf
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkspaceHost
)

$ErrorActionPreference = "Stop"

databricks auth login --host $WorkspaceHost
if ($LASTEXITCODE -ne 0) {
    throw "databricks auth login failed for $WorkspaceHost"
}

$tokenJson = databricks auth token --host $WorkspaceHost | ConvertFrom-Json
if (-not $tokenJson.access_token) {
    throw "databricks auth token returned no access_token for $WorkspaceHost"
}

$env:BIC_AUTH_TOKEN = $tokenJson.access_token
Write-Host "BIC_AUTH_TOKEN set from OAuth U2M session for $WorkspaceHost (length=$($tokenJson.access_token.Length))"
