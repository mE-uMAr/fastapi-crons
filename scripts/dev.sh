#!/bin/bash
# Run development server with example app

set -e

echo "🚀 Starting development server..."
python -m uvicorn examples.app:app --reload --host 0.0.0.0 --port 8000
