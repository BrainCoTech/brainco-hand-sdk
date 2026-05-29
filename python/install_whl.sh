#!/bin/bash
set -e

# BrainCo Stark SDK - Install .whl from OSS
# Usage: bash install_whl.sh [version]
# Example: bash install_whl.sh 2.0.2

OSS_BASE="https://app.brainco.cn/universal/bc-stark-sdk/libs"

# Get version from argument, or read from Cargo.toml, or default
if [ -n "$1" ]; then
  VERSION="$1"
elif [ -f "Cargo.toml" ]; then
  VERSION=$(grep '^version =' Cargo.toml | head -1 | awk -F'"' '{print $2}')
else
  VERSION="2.0.2"
fi

echo "Installing bc-stark-sdk v${VERSION}..."

# Detect platform
OS=$(uname -s)
ARCH=$(uname -m)

case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64) PLATFORM="macosx_11_0_arm64" ;;
      x86_64) PLATFORM="macosx_10_12_x86_64" ;;
      *) echo "Unsupported macOS arch: $ARCH"; exit 1 ;;
    esac
    ;;
  Linux)
    case "$ARCH" in
      x86_64) PLATFORM="manylinux_2_34_x86_64" ;;
      aarch64) PLATFORM="manylinux_2_34_aarch64" ;;
      *) echo "Unsupported Linux arch: $ARCH"; exit 1 ;;
    esac
    ;;
  MINGW*|MSYS*|CYGWIN*)
    PLATFORM="win_amd64"
    ;;
  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

# abi3-cp39 is compatible with Python 3.9+
WHL_NAME="bc_stark_sdk-${VERSION}-cp39-abi3-${PLATFORM}.whl"
WHL_URL="${OSS_BASE}/v${VERSION}/${WHL_NAME}"

# Check if file exists before downloading
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --head "$WHL_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
  echo "Error: v${VERSION} not found on OSS (HTTP $HTTP_CODE)"
  echo "URL: $WHL_URL"
  echo ""
  echo "Try: pip3 install bc-stark-sdk==${VERSION}  (from PyPI)"
  exit 1
fi

echo "Downloading: $WHL_URL"
# Add --break-system-packages if pip supports it (for PEP 668)
PIP_FLAGS=""
if pip3 install --help | grep -q "break-system-packages"; then
  PIP_FLAGS="--break-system-packages"
fi

pip3 install $PIP_FLAGS "$WHL_URL"
echo "Done. bc-stark-sdk v${VERSION} installed."
