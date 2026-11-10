#!/usr/bin/env bash
# Build the Okapi sidecar JAR and put it where the app looks for it:
#   okapi-sidecar/dist/okapi-sidecar.jar
#
# Needs Java 17 or newer and Maven 3.8 or newer.
#   ./build.sh
set -euo pipefail
cd "$(dirname "$0")"

VERSION="0.2.0"

mvn -B -q package -DskipTests
mkdir -p dist
cp "target/okapi-sidecar-$VERSION.jar" dist/okapi-sidecar.jar
echo "Built dist/okapi-sidecar.jar (sidecar $VERSION)"
