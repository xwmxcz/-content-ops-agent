#!/bin/bash
# Standalone production validation test runner
# Must run outside pytest to avoid config module caching

set -e

echo "Running production configuration validation tests..."
echo "===================================================="
echo

cd "$(dirname "$0")/../.."

python3 tests/standalone/test_production_validation.py

echo
echo "===================================================="
echo "All production validation tests passed!"
