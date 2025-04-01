#!/bin/bash

# Script to execute Claude CLI command with proper environment setup
# This script is called by neon_cc_agent.py

# Use environment variables instead of command-line arguments
# PROJECT_FOLDER, CLAUDE_SUBJECT, ANTHROPIC_API_KEY, ALLOWED_TOOLS, and TIMEOUT
# should be set by the calling process

# Set defaults for missing environment variables
PROJECT_FOLDER="${PROJECT_FOLDER:-$1}"
CLAUDE_SUBJECT="${CLAUDE_SUBJECT:-$2}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-$3}"
ALLOWED_TOOLS="${ALLOWED_TOOLS:-$4}"
TIMEOUT="${TIMEOUT:-${5:-240}}"

# Set up logging
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/claude-execution.log"
OUTPUT_FILE="$SCRIPT_DIR/claude-output.txt"

# Timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "=== Claude execution started at $(timestamp) ===" >> "$LOG_FILE" 2>&1
echo "Script directory: $SCRIPT_DIR" >> "$LOG_FILE" 2>&1
echo "Working directory: $(pwd)" >> "$LOG_FILE" 2>&1
echo "Subject: $CLAUDE_SUBJECT" >> "$LOG_FILE" 2>&1
echo "API Key present: $(if [ -n "$ANTHROPIC_API_KEY" ]; then echo "Yes"; else echo "No"; fi)" >> "$LOG_FILE" 2>&1
echo "Allowed tools: $ALLOWED_TOOLS" >> "$LOG_FILE" 2>&1
echo "Timeout: $TIMEOUT seconds" >> "$LOG_FILE" 2>&1

# Change to project folder if provided
if [ -n "$PROJECT_FOLDER" ]; then
  echo "Changing to project folder: $PROJECT_FOLDER" >> "$LOG_FILE" 2>&1
  cd "$PROJECT_FOLDER" || {
    echo "ERROR: Failed to change to project folder: $PROJECT_FOLDER" >> "$LOG_FILE" 2>&1
    echo "ERROR: Failed to change to project folder: $PROJECT_FOLDER"
    exit 1
  }
  echo "Successfully changed to project folder: $(pwd)" >> "$LOG_FILE" 2>&1
fi

# Export API key
export ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"

# Verify Claude CLI is available
if ! command -v claude &> /dev/null; then
  echo "ERROR: Claude CLI not found in PATH" >> "$LOG_FILE" 2>&1
  echo "PATH: $PATH" >> "$LOG_FILE" 2>&1
  echo "ERROR: Claude CLI not found in PATH"
  exit 1
fi

echo "Claude CLI located at: $(which claude)" >> "$LOG_FILE" 2>&1
echo "Claude CLI version: $(claude --version 2>&1)" >> "$LOG_FILE" 2>&1

# Execute Claude CLI command with timeout to prevent hanging
echo "Executing Claude CLI command at $(timestamp)..." >> "$LOG_FILE" 2>&1
echo "Using subject: $CLAUDE_SUBJECT" >> "$LOG_FILE" 2>&1

# Use timeout command to prevent hanging
(
  # The command to run
  timeout "$((TIMEOUT + 30))" claude -p "$CLAUDE_SUBJECT" --allowedTools "$ALLOWED_TOOLS" > "$OUTPUT_FILE" 2>> "$LOG_FILE"
) 

# Capture exit code
EXIT_CODE=$?

# Check if timed out
if [ $EXIT_CODE -eq 124 ]; then
  echo "ERROR: Claude CLI command timed out after $((TIMEOUT + 30)) seconds" >> "$LOG_FILE" 2>&1
  echo "ERROR: Claude CLI command timed out after $((TIMEOUT + 30)) seconds"
fi

# Log completion
echo "Claude CLI command completed at $(timestamp) with exit code: $EXIT_CODE" >> "$LOG_FILE" 2>&1
echo "=== Claude execution completed at $(timestamp) ===" >> "$LOG_FILE" 2>&1

# Output the result
if [ -f "$OUTPUT_FILE" ]; then
  cat "$OUTPUT_FILE"
  echo "Output saved to: $OUTPUT_FILE" >> "$LOG_FILE" 2>&1
else
  echo "No output file generated" >> "$LOG_FILE" 2>&1
fi

# Exit with the same exit code
exit $EXIT_CODE
