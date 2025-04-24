#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import subprocess
import imaplib  # Using standard library imaplib
import email
import email.header
import email.utils
import re
from email.parser import BytesParser
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to INFO for more information
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
    required_vars = ['IMAP_USER', 'IMAP_PASSWORD', 'IMAP_HOST', 'ANTHROPIC_API_KEY']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        logger.error('Please create a .env file or set environment variables')
        sys.exit(1)
    
    # Check for recommended environment variables
    if not os.environ.get('PROJECT_FOLDER'):
        logger.warning('Warning: PROJECT_FOLDER environment variable not set')
        logger.warning('Claude will run in the current directory instead of a specific project folder')

    # Print configuration for debugging (hide password)
    logger.info('IMAP Configuration:')
    logger.info(f"- Server: {os.environ.get('IMAP_HOST')}")
    logger.info(f"- Port: {os.environ.get('IMAP_PORT', '993')}")
    logger.info(f"- User: {os.environ.get('IMAP_USER')}")
    logger.info(f"- TLS Enabled: {os.environ.get('IMAP_TLS', 'true').lower() != 'false'}")
    logger.info(f"- Mailbox: {os.environ.get('IMAP_MAILBOX', 'INBOX')}")
    logger.info('Claude Configuration:')
    logger.info(f"- Project Folder: {os.environ.get('PROJECT_FOLDER', '(current directory)')}")
    logger.info(f"- Anthropic API Key: {'✓ Set' if os.environ.get('ANTHROPIC_API_KEY') else '✗ Not set'}")

# Execute Claude CLI via shell script
def run_claude_cli(subject):
    try:
        github_repo = os.environ.get('GITHUB_REPO_URL', '')
        # Check if project folder is set
        project_folder = os.environ.get('PROJECT_FOLDER', '')
        if not project_folder:
            logger.warning('PROJECT_FOLDER environment variable not set. Using current directory.')
        
        # Prepare the environment for the script
        subject_formatted = subject.replace('\r', '').replace('\n', '  ')
        logger.info(f"Using subject: {subject_formatted[:50]}{'...' if len(subject_formatted) > 50 else ''}")
        
        # Set environment variables for the script
        script_env = os.environ.copy()
        script_env.update({
            'PROJECT_FOLDER': project_folder or '.',
            'CLAUDE_SUBJECT': subject_formatted,
            'ALLOWED_TOOLS': 'Bash,Edit',
            'TIMEOUT': '300',
            'GITHUB_REPO_URL': github_repo
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
            stdout, stderr = process.communicate(timeout=360)
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
=== GitHub email received at {datetime.now().isoformat()} ===
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

# Process a single email
def process_email(msg_data):
    try:
        raw_email = msg_data[0][1]
        
        # Parse the raw email
        parser = BytesParser()
        email_message = parser.parsebytes(raw_email)
        
        # Extract sender information
        from_header = email_message.get('From', '')
        from_addr = email.utils.parseaddr(from_header)[1]
        
        subject = email_message.get('Subject', 'No Subject')
        # Decode subject if needed
        if isinstance(subject, email.header.Header):
            subject = str(subject)
        
        logger.info(f'Extracted email from: {from_addr}')
        logger.info(f'Subject: {subject}')
        
        # Check if the email is from neon-cc-agent1@zerionsoftware.com (case insensitive)
        if 'neon-cc-agent1@zerionsoftware.com' not in from_addr.lower():
            logger.info('Ignoring email - not from GitHub notifications')
            return
        
        logger.info('Processing GitHub notification email...')

        # Extract email body
        body = ""
        html_body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    if content_type == "text/plain":
                        body = part.get_payload(decode=True).decode(charset)
                        logger.info(f'Extracted plain text body using charset: {charset}')
                        break
                    elif content_type == "text/html":
                        html_body = part.get_payload(decode=True).decode(charset)
                        logger.info(f'Found HTML body using charset: {charset}')
                except Exception as e:
                    logger.warning(f'Failed to decode part with charset {charset}: {str(e)}')
                    continue
        else:
            try:
                charset = email_message.get_content_charset() or 'utf-8'
                content_type = email_message.get_content_type()
                payload = email_message.get_payload(decode=True).decode(charset)
                if content_type == "text/plain":
                    body = payload
                elif content_type == "text/html":
                    html_body = payload
                logger.info(f'Extracted {content_type} body using charset: {charset}')
            except Exception as e:
                logger.error(f'Failed to decode email body: {str(e)}')
                return None

        # If no plain text found, try to extract text from HTML
        if not body:
            logger.warning('No text content found in email (plain or HTML)')
            return None

        logger.info(f'Email body length: {len(body)} characters')
        
        # Extract GitHub repository URL using regex
        # Matches HTTPS, SSH URLs, issue URLs, and comment URLs
        github_url_pattern = r'(?:https?://(?:www\.)?github\.com/([^/\s]+/[^/\s#]+)(?:/issues/\d+(?:#\w+-\d+)?)?)'
        match = re.search(github_url_pattern, body)
        
        if match:
            repo_path = match.group(1)
            repo_url = f'https://github.com/{repo_path}'
            logger.info(f'Found GitHub repository URL: {repo_url}')
            logger.debug(f'Original URL: {match.group(0)}')
            logger.debug(f'Email body excerpt:\n{body[:500]}') # Log first 500 chars for debugging
            
            # Store the repo URL in environment for later use
            os.environ['GITHUB_REPO_URL'] = repo_url
            logger.info(f'Repository URL stored in environment: {repo_url}')
            
            # Only run Claude CLI if we found a GitHub repo URL
            return run_claude_cli(subject)
        else:
            logger.warning('No GitHub repository URL found in email body')
            logger.debug(f'Email body excerpt:\n{body[:200]}') # Log first 200 chars when no URL found
            return

    except Exception as e:
        logger.error(f'Error processing email: {str(e)}')

# Connect to IMAP server and check for new emails
def check_emails():
    try:
        # IMAP Configuration
        imap_user = os.environ.get('IMAP_USER')
        imap_password = os.environ.get('IMAP_PASSWORD')
        imap_host = os.environ.get('IMAP_HOST')
        imap_port = int(os.environ.get('IMAP_PORT', '993'))
        imap_use_ssl = os.environ.get('IMAP_TLS', 'true').lower() != 'false'
        imap_mailbox = os.environ.get('IMAP_MAILBOX', 'INBOX')
        
        # Connect to the IMAP server
        if imap_use_ssl:
            mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        else:
            mail = imaplib.IMAP4(imap_host, imap_port)
        
        # Login
        mail.login(imap_user, imap_password)
        
        # Select the mailbox
        mail.select(imap_mailbox)
        
        # Search for unread emails
        status, messages = mail.search(None, 'UNSEEN')
        
        if status != 'OK':
            logger.error('Error searching for emails')
            return
        
        # Get list of email IDs
        email_ids = messages[0].split()
        
        if not email_ids:
            logger.info('No new emails found')
            return
        
        logger.info(f'Found {len(email_ids)} new emails')
        
        # Process each email
        for email_id in email_ids:
            # Fetch the email
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            
            if status != 'OK':
                logger.error(f'Error fetching email ID {email_id}')
                continue
            
            # Process the email
            process_email(msg_data)
            
            # Mark as read
            mail.store(email_id, '+FLAGS', '\\Seen')
        
        # Logout
        mail.close()
        mail.logout()
        
    except Exception as e:
        logger.error(f'IMAP error: {str(e)}')

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
COMMIT_TASK="Review the git status and recent changes, then commit and push them using appropriate commit messages. Use git commands to check status, add files, commit, and push.At the end create pull request"
  
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
    clear_log_files()
    
    # Load environment variables
    load_environment()
    
    # Create Claude script
    create_claude_script()
    
    logger.info('IMAP email checker started')
    logger.info('Polling for emails...')
    
    # Main loop
    polling_interval = 60  # Seconds
    try:
        while True:
            try:
                check_emails()
            except Exception as e:
                logger.error(f"Error during email check: {str(e)}")
            
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
