# Neon Claude Code Agent

A Python application that monitors an IMAP email account for new messages, extracts their content, and passes it to Claude CLI with specified tools.

## Prerequisites

1. **Claude Code CLI**:
   - Install Claude Code CLI from [Claude Code documentation](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview)
   - Log in to your Anthropic account: `claude login`
   - Verify installation: `claude --version`

2. **GitHub CLI**:
   - Install the GitHub CLI from [GitHub CLI documentation](https://cli.github.com/manual/installation)
   - Authenticate with your GitHub account: `gh auth login`
   - Verify installation: `gh --version`

3. **Python**:
   - Python 3.8+ is required

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Configure your IMAP email account:
   - Copy `.env.example` to `.env`
   - Edit `.env` and add your IMAP email credentials and Anthropic API key

## IMAP Configuration

The application requires the following environment variables (in `.env` file or set in your environment):

- `IMAP_USER`: Your email address
- `IMAP_PASSWORD`: Your email password (or app password for accounts with 2FA)
- `IMAP_HOST`: IMAP server hostname (e.g., imap.gmail.com)
- `IMAP_PORT`: IMAP server port (typically 993 for secure IMAP)
- `IMAP_TLS`: Whether to use TLS (true/false)
- `IMAP_MAILBOX`: Which mailbox to check (defaults to "INBOX")
- `ANTHROPIC_API_KEY`: Your Anthropic API key for Claude

### Gmail-specific Setup

If you're using Gmail:
- Use `imap.gmail.com` as your IMAP host
- [Create an app password](https://myaccount.google.com/apppasswords) instead of using your regular password
- Make sure IMAP is enabled in your Gmail settings

## Usage

1. Setup your environment file:
   ```
   cp .env.example .env
   ```
   Then edit the `.env` file with your IMAP email credentials and Anthropic API key.

2. Make the Python script executable:
   ```
   chmod +x neon_cc_agent.py
   ```

3. Start the application:
   ```
   ./neon_cc_agent.py
   ```
   Or:
   ```
   python3 neon_cc_agent.py
   ```

4. The application will:
   - Connect to your IMAP email account
   - Poll for new unread emails every 60 seconds
   - **Only process emails from "notifications@github.com"** (all other emails are ignored)
   - When a GitHub notification email arrives, extract its subject
   - Pass the subject to Claude CLI with the command: `claude -p "subject" --allowedTools "Bash,Edit"`
   - Log Claude's response to the console and append to `claude-responses.log`

## Features

- Monitors an IMAP mailbox for new messages by polling every minute
- Filters emails to only process those from **notifications@github.com**
- Processes unread emails (and marks them as read after processing)
- Executes Claude CLI with email subject
- Allows Claude to perform GitHub operations using GitHub CLI
- Logs all responses to console and a log file
- Automatically reconnects if the IMAP connection is lost

## Troubleshooting

1. **Claude CLI Issues**:
   - Ensure you are properly logged in with `claude login`
   - Check that your Anthropic API key is valid
   - Verify Claude CLI can run independently: `claude -p "Hello"`

2. **GitHub CLI Issues**:
   - Confirm you're authenticated with `gh auth status`
   - Ensure you have appropriate repository permissions

3. **Email Connection Issues**:
   - Verify your IMAP credentials are correct
   - If using Gmail, confirm that "Less secure app access" is enabled or app password is correctly set up

## Node.js Version

An earlier Node.js implementation is available in the `nodejs/` directory for reference.