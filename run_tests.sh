#!/bin/bash
set -e

# Set environment variables for testing
export PYTHONPATH=$(pwd)/backend
export AUTH_USERNAME=test
export AUTH_PASSWORD=test

echo "Running backend tests..."
backend/venv/bin/pytest backend/tests/ "$@"
