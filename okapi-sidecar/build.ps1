# Build the Okapi sidecar JAR and put it where the app looks for it:
#   okapi-sidecar\dist\okapi-sidecar.jar
#
# Needs Java 17 or newer and Maven 3.8 or newer.
#   .\build.ps1
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    $Version = "0.2.0"
    mvn -B -q package -DskipTests
    if ($LASTEXITCODE -ne 0) { throw "Maven build failed" }
    New-Item -ItemType Directory -Force -Path dist | Out-Null
    Copy-Item "target\okapi-sidecar-$Version.jar" "dist\okapi-sidecar.jar" -Force
    Write-Host "Built dist\okapi-sidecar.jar (sidecar $Version)"
}
finally {
    Pop-Location
}
