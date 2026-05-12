#!/data/data/com.termux/files/usr/bin/bash
cd ~
mkdir -p ~/extract_results
P=(
  "태극2장|tGlrUplKHh8"
  "태극3장|ksSqKt0UkWo"
  "태극4장|Lt917gacJho"
  "태극5장|VdqNEAHWCBM"
  "태극6장|jcBwWo4wN7c"
  "태극7장|RI1bX0gUJpo"
  "태극8장|Gr_Je2ZkgkI"
  "고려|mGa60JDtWmg"
  "금강|f4tKh2kNb-U"
)
for entry in "${P[@]}"; do
  name="${entry%|*}"
  vid="${entry#*|}"
  echo "[$(date +%H:%M:%S)] Extracting $name (vid=$vid)..."
  curl -s -X POST http://localhost:8080/extract_sequence \
    -F "youtube_url=https://www.youtube.com/watch?v=$vid" \
    -F "poomsae_name=$name" \
    --max-time 360 \
    -o ~/extract_results/"$name".json
  bytes=$(wc -c < ~/extract_results/"$name".json)
  echo "  -> $bytes bytes"
done
echo "[$(date +%H:%M:%S)] DONE"
