#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('claude-execution.log')
    ]
)
logger = logging.getLogger(__name__)

# Clear log files on startup
def clear_log_files():
    log_files = [
        'claude-errors.log',
        'claude-execution.log', 
        'claude-responses.log',
        'claude-output.txt'
    ]
    for file in log_files:
        try:
            if os.path.exists(file):
                os.unlink(file)
                logger.info(f"Deleted log file: {file}")
        except Exception as e:
            logger.error(f"Failed to delete log file {file}: {str(e)}")

# Load environment variables
def load_environment():
    # Load configuration from .env file if it exists
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logger.info('Loaded environment variables from .env file')
    else:
        logger.warning('Warning: .env file not found or cannot be read')
        logger.warning('You can create one by running: cp .env.example .env')
    
    # Check for required environment variables
    required_vars = ['GITHUB_TOKEN', 'ANTHROPIC_API_KEY']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        logger.error('Please create a .env file or set environment variables')
        sys.exit(1)

def check_webhook_events():
    """Check GitHub notifications for the authenticated user"""
    try:
        headers = {
            'Authorization': f"token {os.environ['GITHUB_TOKEN']}",
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get unread notifications
        logger.info("Fetching GitHub notifications...")
        response = requests.get(
            'https://api.github.com/notifications',
            headers=headers,
            params={'all': 'false'}  # Only get unread notifications
        )
        response.raise_for_status()
        notifications = response.json()
        logger.info(f"Found {len(notifications)} unread notifications")
        
        for notification in notifications:
            try:
                logger.info(f"Raw notification data: {json.dumps(notification, indent=2)}")
                
                # Check if notification has required fields
                if not notification.get('subject') or not notification.get('repository'):
                    logger.warning("Notification missing required fields")
                    continue

                # Only process issue and issue_comment notifications
                notification_type = notification['subject'].get('type')
                logger.info(f"Notification type: {notification_type}")
                if not notification_type or notification_type not in ['Issue', 'IssueComment']:
                    logger.debug(f"Skipping notification type: {notification_type}")
                    requests.patch(
                        notification['url'],
                        headers=headers
                    )
                    continue

                # Get the full issue/comment data
                subject_url = notification['subject'].get('url')
                logger.info(f"Fetching data from: {subject_url}")
                response = requests.get(
                    subject_url,
                    headers=headers
                )
                response.raise_for_status()
                issue_data = response.json()

                # Get issue title and URL
                subject = issue_data.get('title', '')
                issue_url = issue_data.get('html_url')

                # Initialize body with the issue's body content
                body = issue_data.get('body', '')

                # Get the latest comment using comments endpoint
                repo_full_name = notification['repository']['full_name']
                issue_number = issue_data['number']
                comments_url = f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}/comments"
                
                logger.info(f"Fetching comments from: {comments_url}")
                response = requests.get(
                    comments_url,
                    headers=headers,
                )
                response.raise_for_status()
                comments = response.json()
                
                if comments:
                    latest_comment = comments[-1]  # Get the last comment (most recent)
                    body = latest_comment.get('body', '')
                    logger.info(f"Found latest comment (ID: {latest_comment['id']}) created at: {latest_comment['created_at']}")
                else:
                    logger.info("No comments found, using issue body")

                # Skip automated system comments
                system_comment_patterns = [
                    "Claude CLI command completed successfully",
                    "Issue automatically reopened due to new comment",
                    "Added new changes for issue #",
                    "Commit task completed successfully"
                ]
                if any(pattern in body for pattern in system_comment_patterns):
                    logger.info(f"Skipping automated system comment: {body[:100]}...")
                    requests.patch(
                        notification['url'],
                        headers=headers
                    )
                    logger.info("Marked notification as read")
                    continue

                # Skip notifications without comments when issue is closed/reopened/completed
                if not body and (issue_data.get('state') == 'closed' or 
                               issue_data.get('state_reason') in ['reopened', 'completed']):
                    logger.info(f"Skipping notification without comment. State: {issue_data.get('state')}, "
                              f"Reason: {issue_data.get('state_reason', 'unknown')}")
                    requests.patch(
                        notification['url'],
                        headers=headers
                    )
                    logger.info("Marked notification as read")
                    continue

                # If there's a comment on a closed issue, reopen it first
                if body and issue_data.get('state') == 'closed':
                    try:
                        logger.info(f"Found comment on closed issue #{issue_data['number']}, reopening...")
                        repo_full_name = notification['repository']['full_name']
                        issue_api_url = f"https://api.github.com/repos/{repo_full_name}/issues/{issue_data['number']}"
                        
                        # Reopen the issue
                        response = requests.patch(
                            issue_api_url,
                            headers=headers,
                            json={'state': 'open', 'state_reason': None}  # Clear the state reason when reopening
                        )
                        response.raise_for_status()
                        
                        # Add a comment about automatic reopening
                        comment_url = f"{issue_api_url}/comments"
                        response = requests.post(
                            comment_url,
                            headers=headers,
                            json={'body': 'Issue automatically reopened due to new comment with task.'}
                        )
                        response.raise_for_status()
                        
                        logger.info(f"Successfully reopened issue #{issue_data['number']} and added system comment")
                        issue_data['state'] = 'open'  # Update local state to reflect change
                        
                    except Exception as e:
                        logger.error(f"Failed to reopen issue: {str(e)}")
                        # Continue processing anyway since we have a valid comment

                logger.info(f"Raw body content: {body}")
                logger.info(f"Full issue data: {json.dumps(issue_data, indent=2)}")

                # Extract repository information
                repo_url = notification['repository'].get('html_url')
                if not repo_url:
                    logger.warning("No repository URL found in notification")
                    continue
                logger.info(f"Repository: {repo_url}")
                
                # Log all field values before checking
                logger.info("Checking required fields:")
                logger.info(f"Subject: '{subject}'")
                logger.info(f"Body: '{body}'")
                logger.info(f"Repo URL: '{repo_url}'")
                logger.info(f"Issue URL: '{issue_url}'")


                logger.info(f"Processing {'comment on' if notification_type == 'IssueComment' else 'issue'}: {subject}")
                logger.info(f"Body: {body}")
                logger.info(f"Issue URL: {issue_url}")

                # Process with Claude
                os.environ['GITHUB_REPO_URL'] = repo_url
                os.environ['GITHUB_ISSUE_URL'] = issue_url
                run_claude_cli(subject, body)

                # Mark notification as read
                if notification.get('url'):
                    requests.patch(
                        notification['url'],
                        headers=headers
                    )
                    logger.info("Marked notification as read")
                else:
                    logger.warning("Could not mark notification as read - missing URL")

            except Exception as e:
                logger.error(f'Error processing notification: {str(e)}')
                logger.debug(f"Notification data: {json.dumps(notification, indent=2)}")
                continue

    except Exception as e:
        logger.error(f'Error checking notifications: {str(e)}')

# Execute Claude CLI via shell script
def run_claude_cli(subject, comment_content=None):
    try:
        github_repo = os.environ.get('GITHUB_REPO_URL', '')
        github_issue = os.environ.get('GITHUB_ISSUE_URL', '')
        # Check if project folder is set
        project_folder = os.environ.get('PROJECT_FOLDER', '')
        if not project_folder:
            logger.warning('PROJECT_FOLDER environment variable not set. Using current directory.')
        
        # Prepare the environment for the script
        subject_formatted = subject.replace('\r', '').replace('\n', '  ')
        logger.info(f"Using subject: {subject_formatted[:50]}{'...' if len(subject_formatted) > 50 else ''}")
        
        # Format comment content if present
        if comment_content:
            comment_formatted = comment_content.replace('\r', '').replace('\n', '  ')
            logger.info(f"Using comment content: {comment_formatted[:50]}{'...' if len(comment_formatted) > 50 else ''}")
        
        # Set environment variables for the script
        script_env = os.environ.copy()
        script_env.update({
            'PROJECT_FOLDER': project_folder or '.',
            'CLAUDE_SUBJECT': subject_formatted,
            'ALLOWED_TOOLS': 'Bash,Edit',
            'TIMEOUT': '500',
            'GITHUB_REPO_URL': github_repo,
            'GITHUB_ISSUE_URL': github_issue,
            'GITHUB_COMMENT': comment_formatted if comment_content else ''
        })
        
        # Path to the shell script
        script_path = Path(__file__).parent / 'run_claude.sh'
        
       # Ensure script is executable
        if not os.access(script_path, os.X_OK):
            os.chmod(script_path, 0o755)
        
        logger.info('Executing shell script to run Claude CLI...')
        
        # Execute with a timeout (6 minutes)
        process = subprocess.Popen(
            [str(script_path)],
            env=script_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=540)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            logger.error('Command execution timed out after 6 minutes')
        
        # Log execution details
        logger.info(f"Shell script execution completed. Output length: {len(stdout) if stdout else 0} characters")
        
        # First line of output
        if stdout and len(stdout) > 0:
            first_line = stdout.split('\n')[0] or ''
            logger.info(f"First line of output: {first_line[:50]}{'...' if len(first_line) > 50 else ''}")
        
        logger.info('Command execution response:')
        logger.info(stdout)
        
        if stderr:
            logger.error(f'Command stderr: {stderr}')
        
        # Save response to a log file with timestamp
        timestamp = datetime.now().isoformat().replace(':', '-')
        log_entry = f"""
=== GitHub notification received at {datetime.now().isoformat()} ===
Subject: {subject}

Subject Only:
{subject_formatted}

=== Command response ===
{stdout}
{stderr if stderr else ''}
"""
        with open('claude-responses.log', 'a') as f:
            f.write(log_entry)
        
        return stdout
    
    except Exception as e:
        logger.error(f'Error executing command: {str(e)}')
        
        # Get the content of the log file if it exists
        try:
            log_file_path = Path(__file__).parent / 'claude-execution.log'
            if log_file_path.exists():
                with open(log_file_path, 'r') as f:
                    log_content = f.read()
                logger.error('Claude execution log (last 500 characters):')
                logger.error(log_content[-500:])
        except Exception as log_error:
            logger.error(f'Failed to read log file: {str(log_error)}')
        
        # Append error to the log entry
        error_log_entry = f"""
=== Claude CLI ERROR at {datetime.now().isoformat()} ===
{e}
"""
        with open('claude-errors.log', 'a') as f:
            f.write(error_log_entry)
        
        return None

# Create shell script for running Claude CLI
def create_claude_script():
    script_content = '''#!/bin/bash

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
GITHUB_ISSUE_URL="${GITHUB_ISSUE_URL:-$7}"
GITHUB_COMMENT="${GITHUB_COMMENT:-}"

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
echo "GitHub Issue URL: ${GITHUB_ISSUE_URL:-None}" >> "$LOG_FILE" 2>&1
if [ -n "$GITHUB_COMMENT" ]; then
  echo "Using GitHub comment: ${GITHUB_COMMENT:0:50}..." >> "$LOG_FILE" 2>&1
fi

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

# Function to extract issue number from GitHub URL
extract_issue_number() {
  local url="$1"
  if [[ "$url" =~ /issues/([0-9]+) ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi
  return 1
}

# Function to post comment to GitHub issue
post_issue_comment() {
  local issue_number="$1"
  local comment="$2"
  local repo_path="$3"
  
  if [ -n "$issue_number" ] && [ -n "$repo_path" ]; then
    gh issue comment "$issue_number" --body "$comment" --repo "$repo_path"
    return $?
  fi
  return 1
}

# Extract repository information and issue number
REPO_PATH=""
ISSUE_NUMBER=""
if [[ "$GITHUB_REPO_URL" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
  REPO_OWNER="${BASH_REMATCH[1]}"
  REPO_NAME="${BASH_REMATCH[2]}"
  REPO_PATH="$REPO_OWNER/$REPO_NAME"
  
  # Get issue number from GITHUB_ISSUE_URL if available
  if [ -n "$GITHUB_ISSUE_URL" ]; then
    ISSUE_NUMBER=$(extract_issue_number "$GITHUB_ISSUE_URL")
  else
    # Fallback to extracting from subject if needed
    ISSUE_NUMBER=$(extract_issue_number "$CLAUDE_SUBJECT")
  fi
fi

# Execute Claude CLI command with timeout to prevent hanging
echo "Executing Claude CLI command at $(timestamp)..." >> "$LOG_FILE" 2>&1
echo "Using subject: $CLAUDE_SUBJECT" >> "$LOG_FILE" 2>&1
if [ -n "$GITHUB_COMMENT" ]; then
    echo "Using GitHub comment: ${GITHUB_COMMENT:0:50}..." >> "$LOG_FILE" 2>&1
fi

# Use NODE_OPTIONS to prevent file descriptor errors
export NODE_OPTIONS="--no-warnings"

START_TIME=$(date +%s)
{
  if [ -n "$GITHUB_COMMENT" ]; then
        # If we have comment content, combine it with the subject
        PROMPT="Subject: $CLAUDE_SUBJECT\n\nComment: $GITHUB_COMMENT\n\nNote: If the comment contains a new request that conflicts with the original issue, prioritize the comment as it is more recent."
        timeout --kill-after=30 $TIMEOUT claude -p "$PROMPT" --allowedTools "Bash,Edit" 2>&1
    else
        # Otherwise just use the subject
        timeout --kill-after=30 $TIMEOUT claude -p "$CLAUDE_SUBJECT" --allowedTools "Bash,Edit" 2>&1
    fi
} | tee -a "$OUTPUT_FILE" | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "Command execution took $DURATION seconds with exit code $EXIT_CODE" >> "$LOG_FILE" 2>&1

if [ $EXIT_CODE -eq 124 ] || [ $EXIT_CODE -eq 137 ]; then
  ERROR_MSG="ERROR: Claude CLI command timed out after $TIMEOUT seconds (exit code: $EXIT_CODE)"
  echo "$ERROR_MSG" | tee -a "$LOG_FILE"
  post_issue_comment "$ISSUE_NUMBER" "❌ Task failed: $ERROR_MSG" "$REPO_PATH"
  exit $EXIT_CODE
elif [ $EXIT_CODE -ne 0 ]; then
  ERROR_MSG="ERROR: Claude CLI command failed with exit code $EXIT_CODE. Command took $DURATION seconds to complete"
  echo "$ERROR_MSG" | tee -a "$LOG_FILE"
  post_issue_comment "$ISSUE_NUMBER" "❌ Task failed: $ERROR_MSG" "$REPO_PATH"
  exit $EXIT_CODE
else
  SUCCESS_MSG="✅ Claude CLI command completed successfully in $DURATION seconds"
  echo "$SUCCESS_MSG" >> "$LOG_FILE" 2>&1
  post_issue_comment "$ISSUE_NUMBER" "$SUCCESS_MSG" "$REPO_PATH"
fi


echo "Executing commit task at $(timestamp)..." >> "$LOG_FILE" 2>&1
# Check for changes and ask Claude to commit if needed
COMMIT_TASK="I am working on the following:

Issue Subject: $CLAUDE_SUBJECT
Issues Comment: $GITHUB_COMMENT
Issue URL: $GITHUB_ISSUE_URL
Repository: $GITHUB_REPO_URL

Instructions for handling the issue:

1. Check PR status:
   - Search for PRs linked to issue #\${ISSUE_NUMBER}
   - Determine if any PRs are open or closed

2. Handle based on PR status:
   a) If open PR exists:
      - Switch to existing branch
      - Update existing branch
      - Add new changes
      - Push updates
      - Add comment about changes

   b) If only closed PRs exist (reopened issue):
      - Create new branch
      - Add changes
      - Push updates
      - Create new PR

   c) If no PRs exist:
      - Create new branch
      - Add initial changes
      - Push updates
      - Create first PR
      Please process these changes following Git best practices. 
      Note do not commit into main branch."

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

if [ $COMMIT_EXIT_CODE -eq 124 ] || [ $COMMIT_EXIT_CODE -eq 137 ]; then
  ERROR_MSG="ERROR: Commit task timed out after $TIMEOUT seconds (exit code: $COMMIT_EXIT_CODE)"
  echo "$ERROR_MSG" | tee -a "$LOG_FILE"
  post_issue_comment "$ISSUE_NUMBER" "❌ Commit task failed: $ERROR_MSG" "$REPO_PATH"
  exit $COMMIT_EXIT_CODE
elif [ $COMMIT_EXIT_CODE -ne 0 ]; then
  ERROR_MSG="ERROR: Commit task failed with exit code $COMMIT_EXIT_CODE. Command took $DURATION seconds to complete"
  echo "$ERROR_MSG" | tee -a "$LOG_FILE"
  post_issue_comment "$ISSUE_NUMBER" "❌ Commit task failed: $ERROR_MSG" "$REPO_PATH"
  exit $COMMIT_EXIT_CODE
else
  SUCCESS_MSG="✅ Commit task completed successfully in $DURATION seconds"
  echo "$SUCCESS_MSG" >> "$LOG_FILE" 2>&1
  post_issue_comment "$ISSUE_NUMBER" "$SUCCESS_MSG" "$REPO_PATH"
fi

# Output the result
if [ -f "$OUTPUT_FILE" ]; then
  cat "$OUTPUT_FILE"
  echo "Output saved to: $OUTPUT_FILE" >> "$LOG_FILE" 2>&1
else
  echo "No output file generated" >> "$LOG_FILE" 2>&1
fi

# Exit with the same exit code
exit $EXIT_CODE
'''

    # Write the script content to a file
    script_path = Path(__file__).parent / 'run_claude.sh'
    with open(script_path, 'w', newline='\n') as f:
        f.write(script_content)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    logger.info(f'Created Claude execution script at: {script_path}')

# Main function with continuous polling
def main():
    # Clear log files
    #clear_log_files()
    
    # Load environment variables
    load_environment()
    
    # Create Claude script
    create_claude_script()
    
    logger.info('GitHub webhook checker started')
    logger.info('Polling for webhook events...')
    
    # Main loop
    polling_interval = int(os.environ.get('POLLING_INTERVAL', 30))
    try:
        while True:
            try:
                check_webhook_events()
            except Exception as e:
                logger.error(f"Error during webhook check: {str(e)}")
            
            # Wait for next check
            logger.info(f"Waiting {polling_interval} seconds before next check...")
            time.sleep(polling_interval)
    
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
