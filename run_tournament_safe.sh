#!/bin/bash
# Safe tournament runner that captures output to file to prevent TUI control sequences
# from affecting the terminal

OUTPUT_FILE="/tmp/tournament_output_$(date +%s).log"

echo "Running tournament, output will be saved to: $OUTPUT_FILE"

cd /workspaces/LiCode
opencode run "run a tournament with 3 agents for 5 rounds to implement a function that returns the nth fibonacci number. Set log level to INFO." > "$OUTPUT_FILE" 2>&1

echo ""
echo "Tournament complete. Searching for TERMINAL logs..."
echo ""

# Show just the terminal-related logs
grep "\[TERMINAL" "$OUTPUT_FILE" | head -50

echo ""
echo "Full output saved to: $OUTPUT_FILE"
echo "To view: cat $OUTPUT_FILE"
