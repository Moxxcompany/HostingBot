#!/bin/bash
# Quick setup script for running E2E tests

echo "🧪 E2E Test Setup Script"
echo "========================"
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL not set"
    echo "   Please set it in Replit Secrets"
    exit 1
fi

echo "✅ DATABASE_URL is set"

# Set test mode
export TEST_MODE=1
export ENVIRONMENT=test

echo "✅ Test mode enabled"
echo ""

# Run E2E tests
echo "Running E2E payment flow tests..."
echo "=================================="
python tests/e2e_payment_flow.py

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✅ All tests passed!"
    echo "   Ready to publish to production"
else
    echo "❌ Some tests failed"
    echo "   Please fix issues before publishing"
fi

exit $exit_code
