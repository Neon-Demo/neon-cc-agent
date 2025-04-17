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
  timeout "$((TIMEOUT + 30))" claude -p "$CLAUDE_SUBJECT" --allowedTools "$ALLOWED_TOOLS" > "$OUTPUT_FILE" 2>> "$LOG_FILE"
) 

# Capture exit code
EXIT_CODE=$?

# Check if timed out
if [ $EXIT_CODE -eq 124 ]; then
  echo "ERROR: Claude CLI command timed out after $((TIMEOUT + 30)) seconds" >> "$LOG_FILE" 2>&1
  echo "ERROR: Claude CLI command timed out after $((TIMEOUT + 30)) seconds"
  exit $EXIT_CODE
fi

echo "Claude execution completed. Checking for changes to commit..." >> "$LOG_FILE" 2>&1
  
cd "$WORKSPACE"
  
  # Check if there are any changes
  if git status --porcelain | grep -q '^'; then
    echo "Changes detected, asking Claude to review and commit..." >> "$LOG_FILE" 2>&1
    
    # Get git diff for Claude
    GIT_DIFF=$(git diff)
    
    # Create a temporary file for the commit task
    COMMIT_TASK=$(cat << EOF
Review the following git diff and create a descriptive commit message:

$GIT_DIFF

Instructions:
1. Review the changes
2. Create a clear, concise commit message
3. Confirm if we should proceed with the commit
EOF
)
    
    echo "Executing Claude CLI for commit review..." >> "$LOG_FILE" 2>&1
    # Run Claude to review changes and create commit message
    COMMIT_RESPONSE=$(timeout "$((TIMEOUT))" claude -p "$COMMIT_TASK" --allowedTools "Bash" 2>> "$LOG_FILE")
    
    # Extract commit message from Claude's response (first line)
    COMMIT_MSG=$(echo "$COMMIT_RESPONSE" | head -n 1)
    
    # If commit message is not empty, proceed with commit
    if [ -n "$COMMIT_MSG" ]; then
      echo "Using Claude's commit message: $COMMIT_MSG" >> "$LOG_FILE" 2>&1
      
      # Configure Git user for this repository
      git config user.email "neon-cc-agent@github.com"
      git config user.name "Neon CC Agent"
      echo "Configured Git user for repository" >> "$LOG_FILE" 2>&1
      
      # Add all changes
      git add . >> "$LOG_FILE" 2>&1
      
      # Create commit with Claude's message
      if git commit -m "$COMMIT_MSG" >> "$LOG_FILE" 2>&1; then
        echo "Changes committed successfully" >> "$LOG_FILE" 2>&1
        
        # Push changes using GitHub CLI
        if gh auth status >> "$LOG_FILE" 2>&1; then
          CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
          
          # Pull latest changes first
          echo "Pulling latest changes..." >> "$LOG_FILE" 2>&1
          git pull origin "$CURRENT_BRANCH" >> "$LOG_FILE" 2>&1
          
          # Push our changes
          echo "Pushing changes to origin..." >> "$LOG_FILE" 2>&1
          if git push origin "$CURRENT_BRANCH" >> "$LOG_FILE" 2>&1; then
            echo "Changes pushed successfully to origin/$CURRENT_BRANCH" >> "$LOG_FILE" 2>&1
          else
            echo "ERROR: Failed to push changes" >> "$LOG_FILE" 2>&1
          fi
        else
          echo "ERROR: GitHub CLI not authenticated" >> "$LOG_FILE" 2>&1
        fi
      else
        echo "ERROR: Failed to commit changes" >> "$LOG_FILE" 2>&1
      fi
    else
      echo "ERROR: Could not generate commit message from Claude's response" >> "$LOG_FILE" 2>&1
    fi
  else
    echo "No changes detected after Claude execution" >> "$LOG_FILE" 2>&1
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
