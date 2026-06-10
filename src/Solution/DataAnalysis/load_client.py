#!/usr/bin/env python3
"""
experiments/load_client.py
===========================
Concurrent HTTP load client for the FIFO vs SFF web-server experiment.
 
Generates a controlled stream of HTTP GET requests at a target rate and
records per-request latency, file type, and status code.  Outputs both
per-request raw CSV and a one-line summary suitable for the campaign CSV.
 
Architecture
────────────
  Dispatcher thread  →  work_queue  →  N worker threads  →  results list
  
  The dispatcher generates (uri, file_type) tuples at exactly `rate` req/s
  using a token-bucket approach, then signals workers when the run is over.
  Workers consume from the queue, send a raw HTTP/1.0 request over a fresh
  TCP socket, measure round-trip latency, and append to a thread-safe list.
 
Usage
─────
  python3 experiments/load_client.py \\
    --host localhost --port 10000    \\
    --small-dir www/small            \\
    --large-dir www/large            \\
    --small-ratio 0.8                \\
    --rate 100 --duration 60         \\
    --workers 64                     \\
    --scenario B                     \\
    --raw-output results/raw_B_fifo_01.csv   \\
    --summary-output results/campaign.csv    \\
    --policy fifo --replica 1
 
Output columns (raw CSV)
────────────────────────
  ts_ms, file_type, uri, latency_ms, status, bytes_received
 
Output columns (summary CSV — one row appended per replica)
────────────────────────────────────────────────────────────
  scenario, policy, replica,
  n_total, n_small, n_large, n_errors,
  mean_ms, p50_ms, p95_ms, p99_ms,
  mean_ms_small, p95_ms_small, p99_ms_small,
  mean_ms_large, p95_ms_large, p99_ms_large,
  throughput_rps, fairness_cv
"""
 
import argparse
import csv
import os
import queue
import random
import socket
import sys
import threading
import time
from pathlib import Path
 
 
# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────
 
def http_get(host: str, port: int, uri: str, timeout: float = 10.0):
    """
    Send a bare HTTP/1.0 GET, drain the response, return
    (latency_ms, status_code, bytes_received).
    Raises socket.error on network failure.
    """
    t0 = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        req = f"GET {uri} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        sock.sendall(req.encode())
 
        data = bytearray()
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
 
    latency_ms = (time.perf_counter() - t0) * 1000.0
 
    status = 0
    if data:
        first = data.split(b"\r\n", 1)[0].decode(errors="replace")
        parts = first.split()
        if len(parts) >= 2:
            try:
                status = int(parts[1])
            except ValueError:
                pass
 
    return latency_ms, status, len(data)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Worker thread
# ──────────────────────────────────────────────────────────────────────────────
 
def worker_fn(host, port, work_q, results, stop_event, timeout):
    """
    Pull (uri, file_type, enqueue_ts) tuples from work_q, fire HTTP GETs,
    and append (ts_ms, file_type, uri, latency_ms, status, size) to results.
    """
    while True:
        try:
            uri, ftype, _ = work_q.get(timeout=0.3)
        except queue.Empty:
            if stop_event.is_set():
                break
            continue
 
        ts_ms = time.perf_counter() * 1000.0
        try:
            lat, status, size = http_get(host, port, uri, timeout)
            results.append((ts_ms, ftype, uri, lat, status, size))
        except Exception:
            results.append((ts_ms, ftype, uri, -1.0, 0, 0))
        finally:
            work_q.task_done()
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher — token-bucket rate limiter
# ──────────────────────────────────────────────────────────────────────────────
 
def dispatcher_fn(small_uris, large_uris, small_ratio,
                  rate, duration, work_q, stop_event):
    """
    Generate requests at `rate` req/s for `duration` seconds using a
    token-bucket approach, then set stop_event.
    """
    interval   = 1.0 / rate          # ideal gap between dispatches
    deadline   = time.perf_counter() + duration
    tokens     = 1.0
    last_tick  = time.perf_counter()
 
    while True:
        now    = time.perf_counter()
        if now >= deadline:
            break
 
        # Refill tokens
        elapsed = now - last_tick
        tokens  = min(tokens + elapsed * rate, rate)  # cap burst at 1 second
        last_tick = now
 
        if tokens >= 1.0:
            tokens -= 1.0
            # Choose file
            if random.random() < small_ratio:
                uri   = random.choice(small_uris)
                ftype = "small"
            else:
                uri   = random.choice(large_uris)
                ftype = "large"
            work_q.put((uri, ftype, now))
        else:
            time.sleep(interval * 0.5)   # sleep half an interval, re-check
 
    stop_event.set()
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ──────────────────────────────────────────────────────────────────────────────
 
def percentile(data, p):
    if not data:
        return float("nan")
    s = sorted(data)
    idx = (p / 100.0) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] * (1 - frac) + s[hi] * frac
 
 
def coeff_variation(data):
    if len(data) < 2:
        return float("nan")
    mean = sum(data) / len(data)
    if mean == 0:
        return float("nan")
    variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
    return (variance ** 0.5) / mean
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
 
def parse_args():
    p = argparse.ArgumentParser(description="Concurrent HTTP load client")
    p.add_argument("--host",           default="localhost")
    p.add_argument("--port",           type=int, default=10000)
    p.add_argument("--small-dir",      required=True, help="Directory of small HTML files")
    p.add_argument("--large-dir",      required=True, help="Directory of large HTML files")
    p.add_argument("--small-ratio",    type=float, default=0.8,
                   help="Fraction of requests that target small files (0–1)")
    p.add_argument("--rate",           type=float, default=100,
                   help="Target request rate (req/s)")
    p.add_argument("--duration",       type=float, default=60,
                   help="Duration of the load phase in seconds")
    p.add_argument("--workers",        type=int, default=64,
                   help="Number of concurrent worker threads")
    p.add_argument("--timeout",        type=float, default=10.0,
                   help="Per-request socket timeout (seconds)")
    p.add_argument("--scenario",       default="B")
    p.add_argument("--policy",         default="fifo")
    p.add_argument("--replica",        type=int, default=1)
    p.add_argument("--seed",           type=int, default=None,
                   help="Random seed for reproducibility")
    p.add_argument("--raw-output",     default=None,
                   help="Path for per-request CSV (optional)")
    p.add_argument("--summary-output", default=None,
                   help="Path for campaign summary CSV (appended, not replaced)")
    return p.parse_args()
 
 
def main():
    args = parse_args()
 
    # ── Discover files ────────────────────────────────────────────────────────
    small_dir = Path(args.small_dir)
    large_dir = Path(args.large_dir)
 
    small_uris = sorted(f"/{Path(small_dir).name}/{p.name}" for p in small_dir.glob("*.html"))
    large_uris = sorted(f"/{Path(large_dir).name}/{p.name}" for p in large_dir.glob("*.html"))
    if not large_uris and args.small_ratio < 1.0:
        print(f"ERROR: no .html files found in {large_dir}", file=sys.stderr)
        sys.exit(1)
 
    print(f"[load_client] policy={args.policy} scenario={args.scenario} "
          f"replica={args.replica} rate={args.rate} duration={args.duration}s "
          f"workers={args.workers} small_ratio={args.small_ratio}")
    print(f"              small_files={len(small_uris)}  large_files={len(large_uris)}")

    # ── Initialize random seed for reproducibility ────────────────────────────
    if args.seed is not None:
        random.seed(args.seed)

    # ── Set up concurrency primitives ─────────────────────────────────────────
    work_q     = queue.Queue(maxsize=int(args.rate * 3))   # bound burst
    results    = []
    results_lk = threading.Lock()
    stop_event = threading.Event()
 
    # Thread-safe append wrapper
    thread_results = []
    thread_lock    = threading.Lock()
 
    def safe_append(row):
        with thread_lock:
            thread_results.append(row)
 
    # Override worker to use safe_append
    def worker_safe(host, port, work_q, stop_event, timeout):
        while True:
            try:
                uri, ftype, _ = work_q.get(timeout=0.3)
            except queue.Empty:
                if stop_event.is_set():
                    break
                continue
            ts_ms = time.perf_counter() * 1000.0
            try:
                lat, status, size = http_get(host, port, uri, timeout)
                safe_append((ts_ms, ftype, uri, lat, status, size))
            except Exception:
                safe_append((ts_ms, ftype, uri, -1.0, 0, 0))
            finally:
                work_q.task_done()
 
    # ── Start workers ─────────────────────────────────────────────────────────
    workers = []
    for _ in range(args.workers):
        t = threading.Thread(
            target=worker_safe,
            args=(args.host, args.port, work_q, stop_event, args.timeout),
            daemon=True,
        )
        t.start()
        workers.append(t)
 
    # ── Run dispatcher ────────────────────────────────────────────────────────
    t_start = time.perf_counter()
    dispatcher_fn(
        small_uris, large_uris, args.small_ratio,
        args.rate, args.duration, work_q, stop_event,
    )
 
    # Wait for queue to drain (up to 30 extra seconds)
    try:
        work_q.join()
    except Exception:
        pass
 
    t_end = time.perf_counter()
    wall_secs = t_end - t_start
 
    for t in workers:
        t.join(timeout=2)
 
    rows = thread_results
 
    # ── Compute statistics ────────────────────────────────────────────────────
    all_lat   = [r[3] for r in rows if r[3] >= 0]
    small_lat = [r[3] for r in rows if r[3] >= 0 and r[1] == "small"]
    large_lat = [r[3] for r in rows if r[3] >= 0 and r[1] == "large"]
    n_errors  = sum(1 for r in rows if r[3] < 0 or r[4] not in (200,))
 
    n_total = len(rows)
    n_small = len([r for r in rows if r[1] == "small"])
    n_large = len([r for r in rows if r[1] == "large"])
    throughput = (n_total - n_errors) / wall_secs if wall_secs > 0 else 0
 
    def safe_mean(data):
        return sum(data) / len(data) if data else float("nan")
 
    stats = {
        "scenario":       args.scenario,
        "policy":         args.policy,
        "replica":        args.replica,
        "n_total":        n_total,
        "n_small":        n_small,
        "n_large":        n_large,
        "n_errors":       n_errors,
        "mean_ms":        round(safe_mean(all_lat), 3),
        "p50_ms":         round(percentile(all_lat, 50), 3),
        "p95_ms":         round(percentile(all_lat, 95), 3),
        "p99_ms":         round(percentile(all_lat, 99), 3),
        "mean_ms_small":  round(safe_mean(small_lat), 3),
        "p95_ms_small":   round(percentile(small_lat, 95), 3),
        "p99_ms_small":   round(percentile(small_lat, 99), 3),
        "mean_ms_large":  round(safe_mean(large_lat), 3),
        "p95_ms_large":   round(percentile(large_lat, 95), 3),
        "p99_ms_large":   round(percentile(large_lat, 99), 3),
        "throughput_rps": round(throughput, 3),
        "fairness_cv":    round(coeff_variation(all_lat), 5)
                          if all_lat else float("nan"),
    }
 
    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"[load_client] Done:  n={n_total}  errors={n_errors}  "
          f"mean={stats['mean_ms']:.1f} ms  "
          f"p95={stats['p95_ms']:.1f} ms  "
          f"throughput={stats['throughput_rps']:.1f} req/s  "
          f"CV={stats['fairness_cv']:.3f}")
 
    # ── Write raw per-request CSV (optional) ──────────────────────────────────
    if args.raw_output:
        raw_path = Path(args.raw_output)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts_ms", "file_type", "uri", "latency_ms",
                         "status", "bytes_received"])
            w.writerows(rows)
        print(f"[load_client] Raw data → {raw_path}  ({len(rows)} rows)")
 
    # ── Append one row to the campaign summary CSV ────────────────────────────
    if args.summary_output:
        sum_path = Path(args.summary_output)
        sum_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not sum_path.exists()
        with sum_path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(stats.keys()))
            if write_header:
                w.writeheader()
            w.writerow(stats)
        print(f"[load_client] Summary row appended → {sum_path}")
 
 
if __name__ == "__main__":
    main()