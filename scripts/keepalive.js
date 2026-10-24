const https = require('https');

// The URL of your SupremeAI backend on Render
const URL = (process.env.BACKEND_URL) + '/api/v1/health';

console.log('🚀 Starting SupremeAI Keep-Alive Service...');
console.log(`📡 Pinging: ${URL} every 5 minutes`);

setInterval(() => {
  const req = https.get(URL, (res) => {
    console.log(`[${new Date().toISOString()}] Keep-alive ping: ${res.statusCode}`);
  });
  
  req.on('error', (e) => {
    console.error(`[${new Date().toISOString()}] Keep-alive failed: ${e.message}`);
  });
}, 300000); // Every 5 minutes (300,000 ms)
