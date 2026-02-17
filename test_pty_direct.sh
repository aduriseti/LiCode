#!/bin/bash
# Test PTY spawning directly without running full tournament

# Start a single opencode session in background
echo "Starting OpenCode session..."
timeout 60 /home/codespace/.opencode/bin/opencode start --port 0 > /tmp/oc_session.log 2>&1 &
OC_PID=$!

# Wait for it to start and get the port
sleep 3
PORT=$(grep -oP "http://127.0.0.1:\K\d+" /tmp/oc_session.log | head -1)
if [ -z "$PORT" ]; then
    echo "Failed to start OpenCode session"
    kill $OC_PID 2>/dev/null
    exit 1
fi

echo "OpenCode session started on port $PORT"
echo "URL: http://127.0.0.1:$PORT"

# Try to attach via PTY using node-pty
echo "Attempting PTY attach..."
cd /workspaces/LiCode/.opencode && node -e "
const pty = require('node-pty');
const term = pty.spawn('/home/codespace/.opencode/bin/opencode', 
    ['attach', 'http://127.0.0.1:$PORT'],
    {
        name: 'xterm-256color',
        cols: 120,
        rows: 40,
        env: {...process.env, TERM: 'xterm-256color', COLORTERM: 'truecolor'}
    }
);

let dataReceived = false;
term.onData(d => {
    dataReceived = true;
    const clean = d.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
    if(clean.trim().length > 0) {
        console.log('Received:', clean.substring(0,100));
    }
});

term.onExit(e => {
    console.log('Exit:', e);
    console.log('Data received:', dataReceived);
    process.exit(e.exitCode || 0);
});

setTimeout(() => {
    if(!dataReceived) {
        console.log('No data after 5s');
    }
    term.kill();
}, 5000);
"

# Cleanup
kill $OC_PID 2>/dev/null
echo "Test complete"
