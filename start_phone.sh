#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$HOME/taekwondo_app"
termux-wake-lock || true
pkill -f "python server.py" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1
source "$HOME/.gemini_env"
nohup python server.py > server.log 2>&1 &
sleep 2
nohup cloudflared tunnel --url http://localhost:8080 > cf.log 2>&1 &
sleep 6
echo "===SERVER==="
tail -5 server.log
echo "===URL==="
grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' cf.log | head -1 || echo "(URL not yet ready)"
