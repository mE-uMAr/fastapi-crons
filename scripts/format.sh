#!/bin/bash
# Format code with ruff

set -e

echo "🎨 Formatting code with ruff..."
python -m ruff format fastapi_crons tests

echo "✅ Code formatted!"
