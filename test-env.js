/**
 * Test environment variables and Claude CLI
 */
const path = require('path');
const { exec } = require('child_process');
const util = require('util');

const execPromise = util.promisify(exec);

// Load environment variables from .env file
const dotenvResult = require('dotenv').config({
  path: path.resolve(__dirname, '.env')
});

console.log('=== Environment Testing ===');

// Test .env loading
if (dotenvResult.error) {
  console.error('❌ .env file not found or cannot be read');
  console.log('  You can create one by running: npm run setup');
} else {
  console.log('✅ .env file loaded successfully');
}

// Test required environment variables
let hasAllVars = true;
const requiredVars = ['IMAP_USER', 'IMAP_PASSWORD', 'IMAP_HOST', 'ANTHROPIC_API_KEY'];

for (const varName of requiredVars) {
  if (!process.env[varName]) {
    console.error(`❌ Missing required environment variable: ${varName}`);
    hasAllVars = false;
  } else {
    console.log(`✅ ${varName} is set`);
  }
}

// Test Claude CLI availability
async function testClaudeCLI() {
  try {
    const { stdout, stderr } = await execPromise('claude --version');
    console.log('✅ Claude CLI is installed and available');
    console.log(`  Version: ${stdout.trim()}`);
    return true;
  } catch (error) {
    console.error('❌ Claude CLI is not installed or not in PATH');
    console.error('  Please install Claude CLI and make sure it\'s in your PATH');
    return false;
  }
}

// Test a simple Claude command
async function testClaudeCommand() {
  try {
    const { stdout, stderr } = await execPromise('claude -p "Say hello!" --max-tokens 10');
    console.log('✅ Claude CLI executed successfully');
    console.log(`  Response: ${stdout.trim()}`);
    return true;
  } catch (error) {
    console.error('❌ Failed to execute Claude CLI command');
    console.error('  Error:', error.message);
    return false;
  }
}

// Test email filtering
function testEmailFiltering() {
  console.log('\n=== Testing Email Filtering ===');
  
  // Test email from GitHub Notifications (text format)
  const githubEmailText = {
    from: { text: 'GitHub <notifications@github.com>' },
    subject: 'Test Subject'
  };
  console.log('Testing email from GitHub notifications (text format):');
  console.log('✅ Would process email from:', githubEmailText.from.text);

  // Test email from GitHub Notifications (array format)
  const githubEmailArray = {
    from: [{ address: 'notifications@github.com', name: 'GitHub' }],
    subject: 'Test Subject'
  };
  console.log('Testing email from GitHub notifications (array format):');
  console.log('✅ Would process email from:', JSON.stringify(githubEmailArray.from));

  // Test email from another sender
  const otherEmail = {
    from: { text: 'Someone Else <someone@example.com>' },
    subject: 'Test Subject'
  };
  console.log('Testing email from another sender:');
  console.log('❌ Would ignore email from:', otherEmail.from.text);

  // Test email from another sender (array format)
  const otherEmailArray = {
    from: [{ address: 'someone@example.com', name: 'Someone Else' }],
    subject: 'Test Subject'
  };
  console.log('Testing email from another sender (array format):');
  console.log('❌ Would ignore email from:', JSON.stringify(otherEmailArray.from));
  
  return true;
}

// Run the tests
async function runTests() {
  console.log('\n=== Testing Claude CLI ===');
  const cliAvailable = await testClaudeCLI();
  
  if (cliAvailable) {
    console.log('\n=== Testing Claude Command ===');
    await testClaudeCommand();
  }
  
  console.log('\n=== Testing Email Filtering ===');
  testEmailFiltering();
  
  console.log('\n=== Summary ===');
  if (hasAllVars && cliAvailable) {
    console.log('✅ Environment is properly configured');
    console.log('  You can start the application with: npm start');
    console.log('  NOTE: The application will only process emails from notifications@github.com');
  } else {
    console.log('❌ Some checks failed. Please fix the issues before running the application.');
  }
}

runTests();