# Build the Localize Large Windows ZIP.
#
#   .\scripts\build_release.ps1                 release name: LocalizeLarge-1.0.0-win-x64.zip
#   .\scripts\build_release.ps1 -Label preview  LocalizeLarge-1.0.0-preview-win-x64.zip
#
# Needs: Python 3.12 with the packages in requirements.txt and pyinstaller, a JDK 17
# (JAVA_HOME set; jlink and jdeps come with it), and Maven.
#
# Steps: build the sidecar, build a minimal Java runtime, run PyInstaller, add the Java
# runtime and the documents, check the build, zip it, write the checksum and release.json.
# SBOM and code signing are separate steps (Phase 8) and are not done here yet.
param(
    [string]$Label = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"$').Matches[0].Groups[1].Value
$Suffix = if ($Label) { "-$Label" } else { "" }
$ZipName = "LocalizeLarge-$Version$Suffix-win-x64.zip"
$Dist = Join-Path $Root "dist\LocalizeLarge"
$Out = Join-Path $Root "release"

Write-Host "== Localize Large $Version$Suffix =="

# 1. Sidecar
Write-Host "== 1. Okapi sidecar =="
& "$Root\okapi-sidecar\build.ps1"
$Jar = Join-Path $Root "okapi-sidecar\dist\okapi-sidecar.jar"
if (-not (Test-Path $Jar)) { throw "Sidecar JAR not built" }

# 2. Minimal Java runtime (jlink)
Write-Host "== 2. Java runtime (jlink) =="
if (-not $env:JAVA_HOME) { throw "JAVA_HOME is not set" }
$Jdeps = Join-Path $env:JAVA_HOME "bin\jdeps.exe"
$Jlink = Join-Path $env:JAVA_HOME "bin\jlink.exe"
$Modules = (& $Jdeps --ignore-missing-deps --multi-release 17 --print-module-deps $Jar 2>$null | Select-Object -Last 1)
if (-not $Modules -or $Modules -notmatch "java\.base") {
    Write-Host "jdeps gave no module list; using the fallback list"
    $Modules = "java.base,java.xml,java.logging,java.desktop,java.naming,java.sql,java.management"
}
# Okapi loads these by reflection, so jdeps cannot see them.
foreach ($extra in @("java.xml", "java.logging", "java.naming", "java.sql", "java.management", "java.desktop", "jdk.crypto.ec", "jdk.charsets", "jdk.unsupported")) {
    if (($Modules -split ",") -notcontains $extra) { $Modules = "$Modules,$extra" }
}
Write-Host "Java modules: $Modules"
$Jre = Join-Path $Root "build\jre"
if (Test-Path $Jre) { Remove-Item -Recurse -Force $Jre }
& $Jlink --add-modules $Modules --strip-debug --no-man-pages --no-header-files --compress=2 --output $Jre
if ($LASTEXITCODE -ne 0) { throw "jlink failed" }

# 3. PyInstaller
Write-Host "== 3. PyInstaller =="
if (Test-Path (Join-Path $Root "dist")) { Remove-Item -Recurse -Force (Join-Path $Root "dist") }
python -m PyInstaller LocalizeLarge.spec --noconfirm --clean --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
if (-not (Test-Path (Join-Path $Dist "LocalizeLarge.exe"))) { throw "LocalizeLarge.exe was not built" }

# 4. Java runtime and documents
Write-Host "== 4. Java runtime and documents =="
$SidecarDir = Join-Path $Dist "_internal\okapi-sidecar"
Copy-Item -Recurse -Force $Jre (Join-Path $SidecarDir "jre")
foreach ($file in @("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md", "CHANGELOG.md")) {
    Copy-Item -Force (Join-Path $Root $file) $Dist
}
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "docs") | Out-Null
Copy-Item -Recurse -Force (Join-Path $Root "docs\security") (Join-Path $Dist "docs\security")
if (Test-Path (Join-Path $Root "docs\user")) {
    Copy-Item -Recurse -Force (Join-Path $Root "docs\user") (Join-Path $Dist "docs\user")
}

# 5. Checks on the build
Write-Host "== 5. Checks =="
# Packages removed from v1 must not be in the build: look for their package
# folders and for the WebEngine libraries.
$Internal = Join-Path $Dist "_internal"
$ForbiddenFolders = @("fitz", "pymupdf", "vosk", "sounddevice", "boto3", "botocore", "deepl", "pynput", "ahk", "google\generativeai")
$Found = @()
foreach ($folder in $ForbiddenFolders) {
    $path = Join-Path $Internal $folder
    if (Test-Path $path) { $Found += $path }
}
$Found += (Get-ChildItem -Recurse $Dist -File | Where-Object { $_.Name -like "*WebEngine*" } | ForEach-Object { $_.FullName })
if ($Found.Count -gt 0) {
    $Found | Select-Object -First 20 | ForEach-Object { Write-Host "  forbidden: $_" }
    throw "The build contains files of packages that were removed from v1"
}
if (Get-ChildItem -Recurse $Dist -Filter "upx*") { throw "UPX files found in the build" }

# Start the built app on an empty profile and let it close itself.
$SmokeProfile = Join-Path $Root "build\smoke-profile"
if (Test-Path $SmokeProfile) { Remove-Item -Recurse -Force $SmokeProfile }
New-Item -ItemType Directory -Force -Path "$SmokeProfile\Roaming", "$SmokeProfile\Local" | Out-Null
$SavedAppData = $env:APPDATA; $SavedLocal = $env:LOCALAPPDATA
try {
    $env:APPDATA = "$SmokeProfile\Roaming"
    $env:LOCALAPPDATA = "$SmokeProfile\Local"
    $env:LOCALIZELARGE_SMOKE_EXIT_MS = "15000"
    $proc = Start-Process -FilePath (Join-Path $Dist "LocalizeLarge.exe") -PassThru
    if (-not $proc.WaitForExit(180000)) { $proc.Kill(); throw "The built app did not close within 3 minutes" }
    if ($proc.ExitCode -ne 0) {
        $FailLog = "$SmokeProfile\Local\LocalizeLarge\logs\localizelarge.log"
        if (Test-Path $FailLog) {
            Write-Host "---- last 120 lines of the built app's log ----"
            Get-Content $FailLog -Tail 120 | ForEach-Object { Write-Host "  log: $_" }
        } else {
            Write-Host "The built app wrote no log file."
            Get-ChildItem -Recurse $SmokeProfile | Select-Object -First 40 | ForEach-Object { Write-Host "  $($_.FullName)" }
        }
        throw ("The built app exited with code {0} (0x{0:X8})" -f $proc.ExitCode)
    }
}
finally {
    $env:APPDATA = $SavedAppData; $env:LOCALAPPDATA = $SavedLocal
    Remove-Item Env:\LOCALIZELARGE_SMOKE_EXIT_MS -ErrorAction SilentlyContinue
}
$Roaming = (Get-ChildItem "$SmokeProfile\Roaming").Name -join ","
$Local = (Get-ChildItem "$SmokeProfile\Local").Name -join ","
Write-Host "Folders created in APPDATA: $Roaming ; in LOCALAPPDATA: $Local"
if ($Roaming -ne "LocalizeLarge" -or $Local -ne "LocalizeLarge") {
    Get-ChildItem -Recurse "$SmokeProfile\Roaming", "$SmokeProfile\Local" |
        Where-Object { $_.FullName -notlike "*\LocalizeLarge*" } |
        Select-Object -First 60 | ForEach-Object { Write-Host "  unexpected: $($_.FullName)" }
    throw "The built app created unexpected folders"
}
$LogPath = "$SmokeProfile\Local\LocalizeLarge\logs\localizelarge.log"
$Log = Get-Content $LogPath -Raw
if ($Log -notmatch "Okapi sidecar started on 127\.0\.0\.1") {
    Get-Content $LogPath -Tail 60 | ForEach-Object { Write-Host "  log: $_" }
    throw "The built app's sidecar did not start on 127.0.0.1 (see the log lines above)"
}
if (Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dist*" }) { throw "A Java process of the build is still running" }
Write-Host "Smoke test passed: started, sidecar on 127.0.0.1 with the bundled Java, clean exit."

# 6. ZIP, checksum, release.json
Write-Host "== 6. ZIP =="
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Zip = Join-Path $Out $ZipName
Compress-Archive -Path $Dist -DestinationPath $Zip -CompressionLevel Optimal
$Hash = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLower()
"$Hash  $ZipName" | Set-Content -Encoding ascii (Join-Path $Out "$ZipName.sha256")
$Size = (Get-Item $Zip).Length
[ordered]@{
    version         = $Version
    date            = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
    platform        = "windows-x64"
    fileName        = $ZipName
    sizeBytes       = $Size
    sha256          = $Hash
    installerType   = "zip"
    signed          = $false
    publisher       = $null
    certificateType = "none"
    minWindows      = "Windows 10 (64-bit) version 1809 or later, and Windows 11"
    basedOnUpstream = "Supervertaler Workbench 1.10.376 (f83e520)"
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Out "release.json")

Write-Host ("Built {0} ({1:N1} MB), SHA-256 {2}" -f $ZipName, ($Size / 1MB), $Hash)
