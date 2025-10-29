#!/bin/bash
# Install development dependencies

set -e

echo "📦 Installing development dependencies..."

pip install -e ".[dev]"

echo "✅ Development dependencies installed!"
