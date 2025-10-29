#!/bin/bash
# Build the package for distribution

set -e

echo "🔨 Building package..."
python -m build

echo "✅ Package built! Check dist/ directory"
