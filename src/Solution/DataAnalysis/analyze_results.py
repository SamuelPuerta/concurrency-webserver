#!/usr/bin/env python3
"""
analyze_results.py
==================
Statistical analysis and visualization for FIFO vs SFF experiment.

Reads the summary.csv produced by run_experiments.sh and performs:
  - Descriptive statistics per group (mean, std, median, p95, p99, CV)
  - Shapiro-Wilk normality test
  - Mann-Whitney U test (two-sided, non-parametric)
  - Seaborn boxplots and violin plots
  - Summary tables and visualizations

Usage:
  python3 analyze_results.py results/summary.csv

Output:
  - Console report with statistical tests
  - Boxplots: results/boxplot_latency_A.png, etc.
  - Violin plots: results/violin_latency_A.png, etc.
  - Summary table: results/analysis_summary.csv
"""

import sys
import os
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
ALPHA = 0.05
SCENARIOS = ["A", "B", "C"]
SCENARIO_LABELS = {
    "A": "Scenario A: Homogeneous (100% small)",
    "B": "Scenario B: Heterogeneous (80% small, 20% large)",
    "C": "Scenario C: Stress (500 req/s)",
}
METRICS = {
    "mean_ms": "Latency (ms)",
    "throughput_rps": "Throughput (req/s)",
}
POLICY_COLORS = {"fifo": "#4C72B0", "sff": "#DD8452"}
POLICY_ORDER = ["fifo", "sff"]

# ──────────────────────────────────────────────────────────────────────────────
# Statistical helpers
# ──────────────────────────────────────────────────────────────────────────────

def rank_biserial(u_stat, n1, n2):
    """Effect size (rank-biserial correlation) for Mann-Whitney U."""
    return 1.0 - (2.0 * u_stat) / (n1 * n2)

def interpret_effect(r):
    a = abs(r)
    if a < 0.1: return "negligible"
    if a < 0.3: return "small"
    if a < 0.5: return "medium"
    return "large"

def is_normal(p_value):
    return "yes" if p_value >= ALPHA else "no"

def significance_stars(p_value):
    if p_value < 0.001: return "***"
    if p_value < 0.01: return "**"
    if p_value < 0.05: return "*"
    return "ns"

# ──────────────────────────────────────────────────────────────────────────────
# Main analysis
# ──────────────────────────────────────────────────────────────────────────────

def main(csv_path):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found")
        sys.exit(1)

    results_dir = csv_path.parent
    df = pd.read_csv(csv_path)

    # Normalize case
    df["scenario"] = df["scenario"].str.upper()
    df["policy"] = df["policy"].str.lower()

    print("=" * 80)
    print("  FIFO vs SFF — Statistical Analysis Report")
    print(f"  Source: {csv_path.name}")
    print(f"  Total rows: {len(df)}")
    print("=" * 80)

    summary_rows = []
    
    # ── Per-scenario analysis ─────────────────────────────────────────────────
    for scenario in SCENARIOS:
        sc_df = df[df["scenario"] == scenario]
        if sc_df.empty:
            print(f"\n[{scenario}] No data — skipping.")
            continue

        print(f"\n{'─' * 80}")
        print(f"  {SCENARIO_LABELS.get(scenario, scenario)}")
        print(f"{'─' * 80}")

        for metric, m_label in METRICS.items():
            print(f"\n  Metric: {m_label}")
            print(f"  {'─' * 70}")

            groups = {}
            stats_by_policy = {}

            for policy in POLICY_ORDER:
                if metric not in sc_df.columns:
                    print(f"    WARNING: column '{metric}' not present for policy {policy}")
                    continue
                vals = sc_df[sc_df["policy"] == policy][metric].dropna().values

                if len(vals) == 0:
                    print(f"    {policy.upper()}: NO DATA")
                    continue

                groups[policy] = vals

                # Descriptive statistics
                mean = np.mean(vals)
                std = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
                median = np.median(vals)
                p95 = np.percentile(vals, 95) if len(vals) > 0 else float("nan")

                # Normality test
                if len(vals) >= 3:
                    sw_stat, sw_p = stats.shapiro(vals)
                    normal = is_normal(sw_p)
                else:
                    sw_p = 1.0
                    normal = "N/A"

                cv = std / mean if mean != 0 else float("nan")
                print(f"    {policy.upper():5s}  n={len(vals):3d}  "
                      f"mean={mean:10.2f}  std={std:8.2f}  "
                      f"median={median:10.2f}  p95={p95:10.2f}  CV={cv:.3f}  [Shapiro p={sw_p:.4f} → {normal}]")

                summary_rows.append({
                    "scenario": scenario,
                    "policy": policy,
                    "metric": metric,
                    "n": len(vals),
                    "mean": round(mean, 3),
                    "std": round(std, 3),
                    "median": round(median, 3),
                    "p95": round(p95, 3),
                    "p99": round(np.percentile(vals, 99) if len(vals) else float("nan"), 3),
                    "cv": round(cv, 5),
                })

            # ── Mann-Whitney U test ───────────────────────────────────────────
            if "fifo" in groups and "sff" in groups:
                fifo_vals = groups["fifo"]
                sff_vals = groups["sff"]

                u_stat, p_value = stats.mannwhitneyu(
                    fifo_vals, sff_vals, alternative="two-sided")
                r = rank_biserial(u_stat, len(fifo_vals), len(sff_vals))
                stars = significance_stars(p_value)

                print(f"\n    Mann-Whitney U: U={u_stat:.1f}, p={p_value:.4f} {stars}")
                print(f"    Effect size (r): {r:+.3f} ({interpret_effect(r)})")

                # Interpret result
                if p_value < ALPHA:
                    fifo_median = np.median(fifo_vals)
                    sff_median = np.median(sff_vals)
                    if metric == "latency_ms":
                        winner = "FIFO" if fifo_median < sff_median else "SFF"
                        loser = "SFF" if winner == "FIFO" else "FIFO"
                        pct_diff = abs(sff_median - fifo_median) / min(fifo_median, sff_median) * 100
                        print(f"    ✓ {winner} has significantly LOWER latency ({pct_diff:.1f}%)")
                    else:
                        winner = "FIFO" if fifo_median > sff_median else "SFF"
                        loser = "SFF" if winner == "FIFO" else "FIFO"
                        pct_diff = abs(sff_median - fifo_median) / min(fifo_median, sff_median) * 100
                        print(f"    ✓ {winner} has significantly HIGHER throughput ({pct_diff:.1f}%)")
                else:
                    print(f"    ✗ No statistically significant difference")

    # ── Generate visualizations ───────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("  Generating visualizations...")
    print(f"{'=' * 80}\n")

    sns.set_style("whitegrid")
    sns.set_palette("husl")

    for scenario in SCENARIOS:
        sc_df = df[df["scenario"] == scenario]
        if sc_df.empty:
            continue

        for metric, m_label in METRICS.items():
            # ── Boxplot ───────────────────────────────────────────────────────
            fig, ax = plt.subplots(figsize=(7, 5))
            
            sns.boxplot(
                data=sc_df,
                x="policy",
                y=metric,
                order=POLICY_ORDER,
                palette=POLICY_COLORS,
                ax=ax,
                width=0.6,
            )
            
            ax.set_title(f"{m_label}\n{SCENARIO_LABELS.get(scenario, scenario)}", fontsize=12, fontweight="bold")
            ax.set_xlabel("Policy", fontsize=11)
            ax.set_ylabel(m_label, fontsize=11)
            ax.grid(True, alpha=0.3, axis="y")
            
            plt.tight_layout()
            out_file = results_dir / f"boxplot_{metric.split('_')[0]}_{scenario}.png"
            plt.savefig(out_file, dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  [saved] {out_file.name}")

            # ── Violin plot ───────────────────────────────────────────────────
            fig, ax = plt.subplots(figsize=(7, 5))
            
            sns.violinplot(
                data=sc_df,
                x="policy",
                y=metric,
                order=POLICY_ORDER,
                palette=POLICY_COLORS,
                ax=ax,
                inner="quartile",
            )
            
            ax.set_title(f"Distribution: {m_label}\n{SCENARIO_LABELS.get(scenario, scenario)}", fontsize=12, fontweight="bold")
            ax.set_xlabel("Policy", fontsize=11)
            ax.set_ylabel(m_label, fontsize=11)
            ax.grid(True, alpha=0.3, axis="y")
            
            plt.tight_layout()
            out_file = results_dir / f"violin_{metric.split('_')[0]}_{scenario}.png"
            plt.savefig(out_file, dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  [saved] {out_file.name}")

    # ── Summary table visualization ───────────────────────────────────────────
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        csv_out = results_dir / "analysis_summary.csv"
        summary_df.to_csv(csv_out, index=False)
        print(f"\n  [saved] {csv_out.name}")

        # Create a visual summary table
        fig, ax = plt.subplots(figsize=(14, max(4, len(summary_df) * 0.35)))
        ax.axis("off")

        display_cols = ["scenario", "policy", "metric", "n", "mean", "std", "median", "p95", "p99", "cv"]
        col_labels = ["Scenario", "Policy", "Metric", "n", "Mean", "Std", "Median", "p95", "p99", "CV"]

        cell_text = []
        for _, row in summary_df.iterrows():
            cell_text.append([
                row["scenario"],
                row["policy"].upper(),
                row["metric"].split("_")[0],
                int(row["n"]),
                f"{row['mean']:.2f}",
                f"{row['std']:.2f}",
                f"{row['median']:.2f}",
                f"{row['p95']:.2f}",
                f"{row['p99']:.2f}",
                f"{row['cv']:.5f}",
            ])

        table = ax.table(
            cellText=cell_text,
            colLabels=col_labels,
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.1, 1.6)

        fig.suptitle("Statistical Summary: FIFO vs SFF", fontsize=13, fontweight="bold", y=0.98)
        plt.tight_layout()

        fig_out = results_dir / "summary_table.png"
        plt.savefig(fig_out, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  [saved] {fig_out.name}")

    print(f"\n{'=' * 80}")
    print("  Analysis complete.")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <results_csv>")
        print(f"Example: python3 {sys.argv[0]} results/summary.csv")
        sys.exit(1)
    main(sys.argv[1])
