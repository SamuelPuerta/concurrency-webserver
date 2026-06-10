#!/usr/bin/env bash
# experiments/setup_files.sh
#
# Creates the static test files the server will serve during experiments.
# File sizes are DETERMINISTIC: each file is padded with a repeating ASCII
# pattern so the on-disk size matches the target exactly — no random content,
# no tr-filtering that would alter the byte count.
#
# Layout produced
# ───────────────
#   www/
#     small/  small_001.html … small_050.html   (SMALL_BYTES each = 10 KB)
#     large/  large_001.html … large_020.html   (LARGE_BYTES each = 500 KB)
#
# Usage
# ─────
#   bash experiments/setup_files.sh [www_dir]
#   (default www_dir = "www" relative to CWD)
#
# Run once from the project root before run_experiments.sh.
# Existing files are overwritten silently.
 
set -euo pipefail
 
SMALL_BYTES=$(( 10 * 1024 ))      # 10 240 bytes
LARGE_BYTES=$(( 500 * 1024 ))     # 512 000 bytes
N_SMALL=50
N_LARGE=20
WWW_DIR="${1:-www}"
 
# ─────────────────────────────────────────────────────────────────────────────
# write_file <path> <target_bytes>
#   Writes an HTML file whose on-disk size equals <target_bytes> exactly.
#   Header + footer are fixed; interior is padded with repeating 'x'.
# ─────────────────────────────────────────────────────────────────────────────
write_file() {
    local dest="$1"
    local target="$2"
    python3 - "${dest}" "${target}" <<'PYEOF'
import sys, pathlib
dest   = pathlib.Path(sys.argv[1])
target = int(sys.argv[2])
header = b'<html><body><pre>\n'
footer = b'\n</pre></body></html>\n'
needed = target - len(header) - len(footer)
if needed < 0:
    raise ValueError(f"target {target} is too small for the HTML wrapper")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(header + b'x' * needed + footer)
PYEOF
}
 
echo "[setup] Writing ${N_SMALL} small files  (${SMALL_BYTES} B = 10 KB each) …"
for i in $(seq -w 1 "${N_SMALL}"); do
    write_file "${WWW_DIR}/small/small_${i}.html" "${SMALL_BYTES}"
done
echo "        ${WWW_DIR}/small/  — $(du -sh "${WWW_DIR}/small" | cut -f1) total"
 
echo "[setup] Writing ${N_LARGE} large files  (${LARGE_BYTES} B = 500 KB each) …"
for i in $(seq -w 1 "${N_LARGE}"); do
    write_file "${WWW_DIR}/large/large_${i}.html" "${LARGE_BYTES}"
done
echo "        ${WWW_DIR}/large/  — $(du -sh "${WWW_DIR}/large" | cut -f1) total"
 
# ── Byte-exact spot-check ─────────────────────────────────────────────────────
S_CHECK=$(wc -c < "${WWW_DIR}/small/small_001.html")
L_CHECK=$(wc -c < "${WWW_DIR}/large/large_001.html")
 
echo ""
echo "[setup] Verification:"
printf "        small_001.html : %d B  (expected %d)\n" "${S_CHECK}" "${SMALL_BYTES}"
printf "        large_001.html : %d B  (expected %d)\n" "${L_CHECK}" "${LARGE_BYTES}"
 
if [[ "${S_CHECK}" -ne "${SMALL_BYTES}" || "${L_CHECK}" -ne "${LARGE_BYTES}" ]]; then
    echo "[setup] ERROR: size mismatch!" >&2
    exit 1
fi
 
echo "[setup] OK — test files ready in ${WWW_DIR}/"