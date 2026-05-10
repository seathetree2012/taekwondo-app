#!/data/data/com.termux/files/usr/bin/bash
# Start playit agent on phone via proot bind for /etc/resolv.conf
SECRET="9df80eb199e941743016e1b80dad45ff088713194a749dce39e5753c7cc9fda4"
PREFIX="/data/data/com.termux/files/usr"

# Make sure resolv.conf exists
mkdir -p "$PREFIX/etc"
if [ ! -s "$PREFIX/etc/resolv.conf" ]; then
  printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > "$PREFIX/etc/resolv.conf"
fi

# Kill any existing playit (use -x to match basename only — avoid killing this shell)
pkill -x playit 2>/dev/null
pkill -x proot 2>/dev/null
sleep 1

# Start under proot with /etc/resolv.conf bound
nohup proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" \
  "$HOME/bin/playit" -s --secret "$SECRET" start \
  < /dev/null > "$HOME/playit.log" 2>&1 &

disown
echo "started, pid=$!"
