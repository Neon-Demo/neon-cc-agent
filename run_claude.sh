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

# Use NODE_OPTIONS to prevent file descriptor errors
export NODE_OPTIONS="--no-warnings"

START_TIME=$(date +%s)
{
  timeout --kill-after=30 $TIMEOUT claude -p "$CLAUDE_SUBJECT" --allowedTools "Bash,Edit" 2>&1
} | tee -a "$OUTPUT_FILE" | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "Command execution took $DURATION seconds with exit code $EXIT_CODE" >> "$LOG_FILE" 2>&1

if [ $EXIT_CODE -eq 124 ] || [ $EXIT_CODE -eq 137 ]; then
  echo "ERROR: Claude CLI command timed out after $TIMEOUT seconds (exit code: $EXIT_CODE)" | tee -a "$LOG_FILE"
  exit $EXIT_CODE
elif [ $EXIT_CODE -ne 0 ]; then
  echo "ERROR: Claude CLI command failed with exit code $EXIT_CODE" | tee -a "$LOG_FILE"
  echo "Command took $DURATION seconds to complete" | tee -a "$LOG_FILE"
  exit $EXIT_CODE
else
  echo "Claude CLI command completed successfully in $DURATION seconds" >> "$LOG_FILE" 2>&1
fi


echo "Executing commit task at $(timestamp)..." >> "$LOG_FILE" 2>&1
# Check for changes and ask Claude to commit if needed
COMMIT_TASK="Create a new branch for this issue and commit changes: then push them using appropriate commit messages. Use git commands to check status, add files, commit, and push.At the end create pull request"

# Ensure NODE_OPTIONS is still set
export NODE_OPTIONS="--no-warnings"

START_TIME=$(date +%s)
{
  timeout --kill-after=30 $TIMEOUT claude -p "$COMMIT_TASK" --allowedTools "Bash,Edit" 2>&1
} | tee -a "$OUTPUT_FILE" | tee -a "$LOG_FILE"
COMMIT_EXIT_CODE=${PIPESTATUS[0]}
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

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
