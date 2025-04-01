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
            'TIMEOUT': '300'
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
        
        # Check if the email is from notifications@github.com (case insensitive)
        if 'notifications@github.com' not in from_addr.lower():
            logger.info('Ignoring email - not from GitHub notifications')
            return
        
        logger.info('Processing GitHub notification email...')
        
        # Extract email content - prefer text over HTML
        content = ''
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    content = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
                    break
                elif content_type == 'text/html' and not content:
                    # Use HTML content if no text content is found
                    content = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
        else:
            content = email_message.get_payload(decode=True).decode(email_message.get_content_charset() or 'utf-8')
        
        # Remove signature portion (common signature delimiters)
        signature_delimiters = [
            '\n-- \n',
            '\n--\n',
            '\n___\n',
            '\n----- Original Message -----',
            '\n-----Original Message-----',
            '\nSent from my iPhone',
            '\nSent from my iPad'
        ]
        
        for delimiter in signature_delimiters:
            if delimiter in content:
                content = content.split(delimiter)[0].strip()
                logger.info(f'Signature removed using delimiter: {delimiter}')
                break
        
        # Use only the subject for now
        logger.info('Processing email subject only...')
        
        # Pass to Claude CLI
        run_claude_cli(subject)
        
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
    script_content = """#!/bin/bash

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
"""
    
    script_path = Path(__file__).parent / 'run_claude.sh'
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    logger.info(f"Created and made executable: {script_path}")

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