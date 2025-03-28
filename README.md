# Neon Claude Code Agent

An application that monitors an IMAP email account for new messages, extracts their content, and passes it to Claude CLI with specified tools.

## Setup

1. Install dependencies:
   ```
   npm install
   ```

2. Make sure Claude CLI is installed and accessible in your PATH

3. Configure your IMAP email account:
   - Copy `.env.example` to `.env`
   - Edit `.env` and add your IMAP email credentials

## IMAP Configuration

The application requires the following environment variables (in `.env` file or set in your environment):

- `IMAP_USER`: Your email address
- `IMAP_PASSWORD`: Your email password (or app password for accounts with 2FA)
- `IMAP_HOST`: IMAP server hostname (e.g., imap.gmail.com)
- `IMAP_PORT`: IMAP server port (typically 993 for secure IMAP)
- `IMAP_TLS`: Whether to use TLS (true/false)
- `IMAP_MAILBOX`: Which mailbox to check (defaults to "INBOX")

### Gmail-specific Setup

If you're using Gmail:
- Use `imap.gmail.com` as your IMAP host
- [Create an app password](https://myaccount.google.com/apppasswords) instead of using your regular password
- Make sure IMAP is enabled in your Gmail settings

## Usage

1. Setup your environment file:
   ```
   npm run setup
   ```
   Then edit the `.env` file with your IMAP email credentials.

2. Test your environment setup:
   ```
   npm run test-env
   ```
   This will verify that your environment variables are set correctly and that Claude CLI is available.

3. Start the server:
   ```
   npm start
   ```

4. The application will:
   - Connect to your IMAP email account
   - Listen for new unread emails
   - **Only process emails from "notifications@github.com"** (all other emails are ignored)
   - When a GitHub notification email arrives, extract its subject and content
   - Combine the subject and content with the format: `Subject: [subject]\n\n[content]`
   - Pass the combined content to Claude CLI with the command: `claude -p "$(cat temp_file)" --allowedTools "Bash,Edit"`
   - Log Claude's response to the console and append to `claude-responses.log`

## Features

- Monitors an IMAP mailbox for new messages
- Filters emails to only process those from **notifications@github.com**
- Processes unread emails (and marks them as read after processing)
- Executes Claude CLI with email content
- Logs all responses to console and a log file
- Automatically reconnects if the IMAP connection is lost