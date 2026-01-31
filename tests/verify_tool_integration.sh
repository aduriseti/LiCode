#!/bin/bash

TOOL_PATH=".opencode/tools/licode_tournament.ts"

echo "Verifying Tool Integration..."

# 1. Check if tool file exists
if [ -f "$TOOL_PATH" ]; then
    echo "✅ Tool definition found at $TOOL_PATH"
else
    echo "❌ Tool definition NOT found at $TOOL_PATH"
    exit 1
fi

# 2. Verify Python CLI entry point works and matches args
echo "Checking Python CLI..."
HELP_OUTPUT=$(python3 -m licode.cli --help)

if echo "$HELP_OUTPUT" | grep -q "prompt"; then
    echo "✅ CLI accepts 'prompt' argument"
else
    echo "❌ CLI missing 'prompt' argument"
    exit 1
fi

if echo "$HELP_OUTPUT" | grep -q -e "--count"; then
    echo "✅ CLI accepts '--count' argument"
else
    echo "❌ CLI missing '--count' argument"
    exit 1
fi

if echo "$HELP_OUTPUT" | grep -q -e "--budget"; then
    echo "✅ CLI accepts '--budget' argument"
else
    echo "❌ CLI missing '--budget' argument"
    exit 1
fi

echo "Integration verification successful."
exit 0
