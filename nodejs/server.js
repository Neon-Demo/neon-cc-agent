const notifier = require('mail-notifier');
const { simpleParser } = require('mailparser');
const { exec } = require('child_process');
const util = require('util');
const fs = require('fs');
const path = require('path');

const execPromise = util.promisify(exec);

// Load configuration from .env file if it exists
const dotenvResult = require('dotenv').config({
  path: path.resolve(__dirname, '.env')
});

if (dotenvResult.error) {
  console.warn('Warning: .env file not found or cannot be read');
  console.warn('You can create one by running: npm run setup');
} else {
  console.log('Loaded environment variables from .env file')
}

// IMAP Configuration - preferably from environment variables
const imapConfig = {
  user: process.env.IMAP_USER,
  password: process.env.IMAP_PASSWORD,
  host: process.env.IMAP_HOST,
  port: parseInt(process.env.IMAP_PORT || '993', 10),
  tls: process.env.IMAP_TLS !== 'false',
  tlsOptions: { rejectUnauthorized: false },
  markSeen: true, // Mark emails as read when processed
  mailbox: process.env.IMAP_MAILBOX || 'INBOX',
  searchFilter: ['UNSEEN'], // Only get unread messages
};

// Project folder for Claude operation
const projectFolder = process.env.PROJECT_FOLDER || '';

// Create a function to process emails
async function processEmail(mail) {
  try {
    // Debug output to see the full structure
    console.log('Debug - mail.from:', JSON.stringify(mail.from, null, 2));
    
    // Extract sender information - handle different possible formats
    let fromEmail = '';
    
    if (typeof mail.from === 'string') {
      // Simple string format
      fromEmail = mail.from;
    } else if (Array.isArray(mail.from)) {
      // Array format [{ address, name }]
      fromEmail = mail.from[0]?.address || '';
    } else if (mail.from?.text) {
      // Object with text property
      fromEmail = mail.from.text;
    } else if (mail.from?.value && Array.isArray(mail.from.value)) {
      // Object with value array property
      fromEmail = mail.from.value[0]?.address || '';
    } else if (mail.from?.address) {
      // Object with direct address property
      fromEmail = mail.from.address;
    }
    
    console.log('Extracted email from:', fromEmail);
    console.log('Subject:', mail.subject);
    
    // Check if the email is from notifications@github.com (case insensitive)
    const isFromGitHub = fromEmail.toLowerCase().includes('notifications@github.com') || 
                         (Array.isArray(mail.from) && mail.from.some(addr => 
                           addr.address && addr.address.toLowerCase().includes('notifications@github.com')));
    
    if (!isFromGitHub) {
      console.log('Ignoring email - not from GitHub notifications');
      return;
    }
    
    console.log('Processing GitHub notification email...');
    
    // Extract email content - prefer text over HTML
    let content = mail.text || mail.html || '';
    const subject = mail.subject || 'No Subject';
    
    // Remove signature portion (common signature delimiters)
    const signatureDelimiters = [
      '\n-- \n',
      '\n--\n',
      '\n___\n',
      '\n----- Original Message -----',
      '\n-----Original Message-----',
      '\nSent from my iPhone',
      '\nSent from my iPad'
    ];
    
    for (const delimiter of signatureDelimiters) {
      if (content.includes(delimiter)) {
        content = content.split(delimiter)[0].trim();
        console.log('Signature removed using delimiter:', delimiter);
        break;
      }
    }
    
    // Use only the subject for now
    const subject_formatted = subject.replace(/\r?\n/g, '  ');
    
    console.log('Processing email subject only...');
    
    try {
      // Check if project folder is set
      if (!projectFolder) {
        console.warn('PROJECT_FOLDER environment variable not set. Using current directory.');
      }
      
      // Execute Claude CLI via shell script
      const scriptPath = path.resolve(__dirname, 'run-claude.sh');
      const allowedTools = "Bash,Edit";
      const timeout = 300;
      
      // Use environment variables instead of command-line arguments
      const env = {
        ...process.env,
        PROJECT_FOLDER: projectFolder || '.',
        CLAUDE_SUBJECT: subject_formatted, 
        ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
        ALLOWED_TOOLS: allowedTools,
        TIMEOUT: timeout.toString()
      };
      
      console.log('Executing shell script to run Claude CLI...');
      console.log(`Using subject: ${subject_formatted.substring(0, 50)}${subject_formatted.length > 50 ? '...' : ''}`);
      
      // Execute with a timeout longer than the script's internal timeout
      const { stdout, stderr } = await execPromise(`"${scriptPath}"`, { 
        timeout: 360000, // 6 minute timeout
        env: env 
      });
      
      // Log execution details
      console.log(`Shell script execution completed. Output length: ${stdout?.length || 0} characters`);
      // First line of output
      if (stdout && stdout.length > 0) {
        const firstLine = stdout.split('\n')[0] || '';
        console.log(`First line of output: ${firstLine.substring(0, 50)}${firstLine.length > 50 ? '...' : ''}`);
      }
      
      console.log('Command execution response:');
      console.log(stdout);
      
      if (stderr) {
        console.error('Command stderr:', stderr);
      }
      
      // Optional: Save response to a log file with timestamp
      const timestamp = new Date().toISOString().replace(/:/g, '-');
      const logEntry = `
=== GitHub email received at ${new Date().toISOString()} ===
From: ${fromEmail}
Subject: ${subject}
Original Content:
${content}

Subject Only:
${subject_formatted}

=== Command response ===
${stdout}
${stderr ? `\nStderr: ${stderr}` : ''}
`;
      
      fs.appendFileSync('claude-responses.log', logEntry);
      
    } catch (cmdError) {
      console.error('Error executing command:', cmdError.message);
      
      // Get the content of the log file if it exists
      try {
        const logFilePath = path.resolve(__dirname, 'claude-execution.log');
        if (fs.existsSync(logFilePath)) {
          const logContent = fs.readFileSync(logFilePath, 'utf8');
          console.error('Claude execution log (last 500 characters):');
          console.error(logContent.slice(-500));
        }
      } catch (logError) {
        console.error('Failed to read log file:', logError.message);
      }
      
      // Append error to the log entry - avoid duplicate error messages
      const errorLogEntry = `
=== Claude CLI ERROR at ${new Date().toISOString()} ===
${cmdError.stack || cmdError.message || 'Unknown error'}
`;
      fs.appendFileSync('claude-errors.log', errorLogEntry);
    }
  } catch (err) {
    console.error('Error processing email:', err);
  }
}

// Check for required environment variables
if (!process.env.IMAP_USER || !process.env.IMAP_PASSWORD || !process.env.IMAP_HOST || !process.env.ANTHROPIC_API_KEY) {
  console.error('Error: Missing required environment variables (IMAP_USER, IMAP_PASSWORD, IMAP_HOST, ANTHROPIC_API_KEY)');
  console.error('Please create a .env file or set environment variables');
  process.exit(1);
}

// Check for recommended environment variables
if (!process.env.PROJECT_FOLDER) {
  console.warn('Warning: PROJECT_FOLDER environment variable not set');
  console.warn('Claude will run in the current directory instead of a specific project folder');
}

// Print configuration for debugging (hide password)
console.log('IMAP Configuration:');
console.log('- Server:', process.env.IMAP_HOST);
console.log('- Port:', process.env.IMAP_PORT || '993');
console.log('- User:', process.env.IMAP_USER);
console.log('- TLS Enabled:', process.env.IMAP_TLS !== 'false');
console.log('- Mailbox:', process.env.IMAP_MAILBOX || 'INBOX');
console.log('Claude Configuration:');
console.log('- Project Folder:', process.env.PROJECT_FOLDER || '(current directory)');
console.log('- Anthropic API Key:', process.env.ANTHROPIC_API_KEY ? '✓ Set' : '✗ Not set');

// Clear log files on startup for clarity
const logFiles = [
  path.resolve(__dirname, 'claude-errors.log'),
  path.resolve(__dirname, 'claude-execution.log'),
  path.resolve(__dirname, 'claude-responses.log'),
  path.resolve(__dirname, 'claude-output.txt')
];

logFiles.forEach(file => {
  try {
    if (fs.existsSync(file)) {
      fs.unlinkSync(file);
      console.log(`Deleted log file: ${file}`);
    }
  } catch (err) {
    console.error(`Failed to delete log file ${file}:`, err.message);
  }
});

// Start the IMAP notifier
const imap = notifier(imapConfig);

imap.on('mail', processEmail);

imap.on('error', (err) => {
  console.error('IMAP error:', err);
});

imap.on('end', () => {
  console.log('IMAP connection ended. Attempting to reconnect...');
  setTimeout(() => {
    try {
      imap.start();
    } catch (err) {
      console.error('Failed to restart IMAP connection:', err);
    }
  }, 10000); // Try to reconnect after 10 seconds
});

// Start the notifier
imap.start();

console.log('IMAP email notifier started');
console.log('Listening for emails...');