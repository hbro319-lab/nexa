#!/usr/bin/env bash
# ============================================================
#  NEXA v2.0 — Linux Build Script
#  Creates the 'nexa' binary using PyInstaller
# ============================================================
set -e

echo ""
echo "  ==================================="
echo "   NEXA v2.0 — Building Linux binary"
echo "  ==================================="
echo ""

# Install dependencies
echo "[1/3] Installing dependencies..."
pip install -r requirements.txt
pip install pyinstaller

# Clean previous build
echo "[2/3] Cleaning previous build..."
rm -rf dist/ build/

# Build
echo "[3/3] Building nexa binary..."
pyinstaller nexa.spec

if [ -f "dist/nexa" ]; then
    echo ""
    echo "  ==================================="
    echo "   BUILD SUCCESSFUL!"
    echo "   Output: dist/nexa"
    echo "  ==================================="
    echo ""
    echo "  Usage:"
    echo "    ./dist/nexa                   Interactive CLI"
    echo "    ./dist/nexa --server          Start dispatch server"
    echo "    ./dist/nexa --gui             Open web UI + server"
    echo "    ./dist/nexa --search 'chrome' Search installed apps"
    echo ""
    echo "  Copy nexa_interface.html and nexa_config.json"
    echo "  to the same folder as the binary for full functionality."
    echo ""
    # Copy required data files
    cp nexa_interface.html dist/ 2>/dev/null || true
    cp nexa_config.json dist/ 2>/dev/null || true
    echo "  Data files copied to dist/"
else
    echo ""
    echo "  [ERROR] Build failed. Check the output above."
    echo ""
    exit 1
fi
