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
GITHUB_REPO_URL="${GITHUB_REPO_URL:-$6}"

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
echo "GitHub Repo URL: ${GITHUB_REPO_URL:-None}" >> "$LOG_FILE" 2>&1

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

# Check if GitHub CLI is available and authenticated
if ! command -v gh &> /dev/null; then
  echo "WARNING: GitHub CLI not found in PATH - skipping repo clone" >> "$LOG_FILE" 2>&1
else
  echo "GitHub CLI found at: $(which gh)" >> "$LOG_FILE" 2>&1
  
  # Check if gh cli is authenticated
  if ! gh auth status &> /dev/null; then
    echo "WARNING: GitHub CLI not authenticated - skipping repo clone" >> "$LOG_FILE" 2>&1
  else
    echo "GitHub CLI authenticated successfully" >> "$LOG_FILE" 2>&1
    
    # If we have a GitHub repo URL, try to clone it
    if [ -n "$GITHUB_REPO_URL" ]; then
      echo "Cloning repository from: $GITHUB_REPO_URL" >> "$LOG_FILE" 2>&1
      
      # Extract repo owner and name from URL
      if [[ "$GITHUB_REPO_URL" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
        REPO_OWNER="${BASH_REMATCH[1]}"
        REPO_NAME="${BASH_REMATCH[2]}"
        
        # Create a clean workspace directory with repo name
        WORKSPACE="$PROJECT_FOLDER/workspace/$REPO_OWNER/$REPO_NAME"
        rm -rf "$WORKSPACE"
        mkdir -p "$WORKSPACE"
        cd "$WORKSPACE"
        pwd >> "$LOG_FILE" 2>&1
        
        # Clone using gh cli which handles auth automatically
        if gh repo clone "$REPO_OWNER/$REPO_NAME" .; then
          echo "Successfully cloned repository to: $WORKSPACE" >> "$LOG_FILE" 2>&1
          # Update PROJECT_FOLDER to point to the cloned repo
          PROJECT_FOLDER="$WORKSPACE"
        else
          echo "Failed to clone repository" >> "$LOG_FILE" 2>&1
        fi
      else
        echo "ERROR: Invalid GitHub URL format: $GITHUB_REPO_URL" >> "$LOG_FILE" 2>&1
      fi
    fi
  fi
fi

# Execute Claude CLI command with timeout to prevent hanging
echo "Executing Claude CLI command at $(timestamp)..." >> "$LOG_FILE" 2>&1
echo "Using subject: $CLAUDE_SUBJECT" >> "$LOG_FILE" 2>&1

# Use timeout command to prevent hanging
(
  # The command to run
  timeout "$((TIMEOUT + 30))" claude -p "$CLAUDE_SUBJECT" --allowedTools "Bash,Edit" > "$OUTPUT_FILE" 2>> "$LOG_FILE"
) 

# Capture exit code
EXIT_CODE=$?

# Check if timed out
if [ $EXIT_CODE -eq 124 ]; then
  echo "ERROR: Claude CLI command timed out after $((TIMEOUT + 30)) seconds" >> "$LOG_FILE" 2>&1
  echo "ERROR: Claude CLI command timed out after $((TIMEOUT + 30)) seconds"
  exit $EXIT_CODE
fi

# Check for changes and ask Claude to commit if needed
COMMIT_TASK="Review the git status and recent changes, then commit and push them using appropriate commit messages. Use git commands to check status, add files, commit, and push."
  
timeout "$((TIMEOUT))" claude -p "$COMMIT_TASK" --allowedTools "Bash,Edit" >> "$OUTPUT_FILE" 2>> "$LOG_FILE"

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
