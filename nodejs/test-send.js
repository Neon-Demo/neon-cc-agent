const nodemailer = require('nodemailer');

// Create transporter
const transporter = nodemailer.createTransport({
  host: 'localhost',
  port: 2525,
  secure: false,
  tls: {
    rejectUnauthorized: false
  }
});

// Email content
const emailContent = process.argv[2] || 'Please help me with this task: create a new file called test.txt with the content "Hello World"';

// Send mail
async function sendTestEmail() {
  try {
    const info = await transporter.sendMail({
      from: 'user@example.com',
      to: 'agent@example.com',
      subject: 'Claude Task Request',
      text: emailContent
    });
    
    console.log('Test email sent successfully!');
    console.log('Message ID:', info.messageId);
  } catch (error) {
    console.error('Failed to send test email:', error);
  }
}

sendTestEmail();