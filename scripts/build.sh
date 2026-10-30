#!/usr/bin/env bash
# 소스만 zip으로 묶어 Lambda 배포 아티팩트를 만든다.
# 런타임 의존성이 없으므로 src/git_file_watcher 를 zip 루트에 그대로 담는다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist"
ZIP="${DIST}/function.zip"

rm -rf "${DIST}"
mkdir -p "${DIST}"

# src 디렉터리 기준으로 압축해야 zip 안에서 import 경로가
# git_file_watcher/... 가 된다. (핸들러: git_file_watcher.handler.lambda_handler)
cd "${ROOT}/src"
zip -r -q "${ZIP}" git_file_watcher -x '*/__pycache__/*'

echo "빌드 완료: ${ZIP}"
