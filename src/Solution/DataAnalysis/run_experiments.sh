#!/usr/bin/env bash
# experiments/run_experiments.sh
#
# Orchestrates the full experiment campaign for the FIFO vs SFF comparison.
# Executes:
#   - Scenario A (homogeneous): 100% small files
#   - Scenario B (heterogeneous): 80% small, 20% large
#   - Scenario C (stress): high rate with 80% small, 20% large
#
# For each scenario:
#   - 50 replicas with FIFO policy
#   - 50 replicas with SFF policy
#
# Outputs:
#   - results/raw_<scenario>_<policy>_<replica>.csv  (per-request details)
#   - results/summary.csv  (one row per replica, aggregated metrics)
#
# Requirements:
#   - WebServer/wserver compiled
#   - DataAnalysis/www/small/ and DataAnalysis/www/large/ populated
#   - python3 with load_client.py available in this directory
#   - PORT 10000 available (or adjust --port below)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WEB_DIR="${ROOT_DIR}/WebServer"
RESULTS_DIR="${SCRIPT_DIR}/results"
WWW_DIR="${SCRIPT_DIR}/www"
WSERVER="${WEB_DIR}/wserver"
LOAD_CLIENT="${SCRIPT_DIR}/load_client.py"

PORT=10000
REPLICAS=50

# ── Colors for output ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [[ ! -x "${WSERVER}" ]]; then
    echo -e "${RED}ERROR: ${WSERVER} not found or not executable${NC}"
    echo "  Run 'make' first to compile the server."
    exit 1
fi

if [[ ! -d "${WWW_DIR}/small" ]] || [[ ! -d "${WWW_DIR}/large" ]]; then
    echo -e "${RED}ERROR: ${WWW_DIR}/small or ${WWW_DIR}/large not found${NC}"
    echo "  Run 'bash setup_files.sh www' first."
    exit 1
fi

if [[ ! -f "${LOAD_CLIENT}" ]]; then
    echo -e "${RED}ERROR: ${LOAD_CLIENT} not found${NC}"
    exit 1
fi

# ── Prepare results directory ─────────────────────────────────────────────────
rm -rf "${RESULTS_DIR}"
mkdir -p "${RESULTS_DIR}"

# Initialize summary CSV with headers
cat > "${RESULTS_DIR}/summary.csv" << 'CSVEOF'
scenario,policy,replica,n_total,n_small,n_large,n_errors,mean_ms,p50_ms,p95_ms,p99_ms,mean_ms_small,p95_ms_small,p99_ms_small,mean_ms_large,p95_ms_large,p99_ms_large,throughput_rps,fairness_cv
CSVEOF

echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}  FIFO vs SFF Web Server Experiment Campaign${NC}"
echo -e "${GREEN}========================================================${NC}"
    echo "  Project root: ${ROOT_DIR}"
    echo "  Web server: ${WEB_DIR}"
    echo "  Data analysis: ${SCRIPT_DIR}"
echo "  Results: ${RESULTS_DIR}/"
echo "  Replicas per (policy, scenario): ${REPLICAS}"
echo "  Total jobs: 3 scenarios × 2 policies × ${REPLICAS} replicas = $((3 * 2 * REPLICAS))"
echo ""

# ── Scenario parameters: scenario_name, small_ratio, rate, duration, server_threads ─
declare -a SCENARIOS=(
    "A:1.0:100:60:8"     # A: homogeneous (100% small), rate=100, duration=60s, threads=8
    "B:0.7:100:60:8"     # B: heterogeneous (70% small), rate=100, duration=60s, threads=8
    "C:0.8:500:60:12"    # C: stress (500 req/s, 80% small), threads=12
)

POLICIES=("fifo" "sff")

# ── Campaign loop ─────────────────────────────────────────────────────────────
TOTAL_JOBS=$((3 * 2 * REPLICAS))
JOBS_DONE=0

for scenario_spec in "${SCENARIOS[@]}"; do
    IFS=':' read -r scenario small_ratio rate duration server_threads <<< "${scenario_spec}"
    
    echo -e "${YELLOW}Scenario ${scenario}: small_ratio=${small_ratio}, rate=${rate} req/s, duration=${duration}s${NC}"
    
    for policy in "${POLICIES[@]}"; do
        echo "  Policy: ${policy} (50 replicas)"
        
        for replica in $(seq -w 1 ${REPLICAS}); do
            JOBS_DONE=$((JOBS_DONE + 1))
            PROGRESS="[$((JOBS_DONE))/${TOTAL_JOBS}]"
            
            # ── Start server in background ────────────────────────────────────────
            "${WSERVER}" \
                -d "${WWW_DIR}" \
                -p "${PORT}" \
                -t "${server_threads}" \
                -b 16 \
                -s "${policy}" \
                > "/tmp/wserver_${scenario}_${policy}_${replica}.log" 2>&1 &
            SERVER_PID=$!
            
            # Wait for server to start
            sleep 1
            
            # ── Run load client ───────────────────────────────────────────────────
            if python3 "${LOAD_CLIENT}" \
                --host localhost \
                --port "${PORT}" \
                --small-dir "${WWW_DIR}/small" \
                --large-dir "${WWW_DIR}/large" \
                --small-ratio "${small_ratio}" \
                --rate "${rate}" \
                --duration "${duration}" \
                --workers 64 \
                --timeout 30.0 \
                --scenario "${scenario}" \
                --policy "${policy}" \
                --replica "${replica}" \
                --seed "${replica}" \
                --raw-output "${RESULTS_DIR}/raw_${scenario}_${policy}_${replica}.csv" \
                --summary-output "${RESULTS_DIR}/summary.csv" \
                > "/tmp/load_${scenario}_${policy}_${replica}.log" 2>&1; then
                
                printf "${PROGRESS} ${GREEN}✓${NC} Scenario=${scenario} Policy=${policy} Replica=${replica}\n"
            else
                printf "${PROGRESS} ${RED}✗${NC} Scenario=${scenario} Policy=${policy} Replica=${replica}\n"
                cat "/tmp/load_${scenario}_${policy}_${replica}.log" | head -20 >&2
            fi
            
            # ── Stop server ───────────────────────────────────────────────────────
            kill "${SERVER_PID}" 2>/dev/null || true
            wait "${SERVER_PID}" 2>/dev/null || true
            
            # Small pause before next replica
            sleep 1
        done
    done
done

echo ""
echo -e "${GREEN}========================================================${NC}"
echo -e "${GREEN}  Campaign complete!${NC}"
echo -e "${GREEN}========================================================${NC}"
echo "Results saved to: ${RESULTS_DIR}/"
echo ""
echo "Files generated:"
echo "  • raw_<scenario>_<policy>_<replica>.csv  (per-request latency data)"
echo "  • summary.csv  (aggregated metrics)"
echo ""
echo "Next step: run analysis"
echo "  python3 analyze_results.py ${RESULTS_DIR}/summary.csv"
