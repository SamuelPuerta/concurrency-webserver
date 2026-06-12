# Concurrent Web Server Project

## Overview

This project implements a concurrent web server in C for the Operating Systems final assignment.
The original reference implementation is in the folder `CodeBase/`, this reference is a Mono-Threaded Web Server fron _OSTEP Projects_, while the completed solution is in the `Solution/` directory.

The goal of the project is to compare two scheduling policies for serving requests:

- FIFO, which serves requests in arrival order.
- SFF, which serves the shortest file first.

The solution keeps the server concurrent, adds automation for reproducible experiments, and provides
statistical analysis for the collected performance data.

## Project Structure

The `Solution/` folder is split into two parts:

- `WebServer/`: server-side C sources and the Makefile.
- `DataAnalysis/`: experiment scripts, data-generation scripts, and analysis outputs.

`WebServer/` contains:

- `wserver.c`: concurrent server entry point.
- `buffer.c` and `buffer.h`: shared request buffer with FIFO and SFF scheduling.
- `request.c` and `request.h`: request processing helpers.
- `io_helper.c` and `io_helper.h`: I/O support utilities.
- `Makefile`: builds the server binary.

`DataAnalysis/` contains:

- `load_client.py`: load generator used to create controlled request campaigns.
- `setup_files.sh`: creates the test document root with small and large files.
- `run_experiments.sh`: runs the full benchmark campaign.
- `analyze_results.py`: processes the collected data and generates statistics and plots.
- `results/`: output directory with raw CSV files, summaries, and figures.

## Solution Summary

The server accepts multiple clients concurrently using a thread pool. Incoming requests are placed in a
buffer and later selected according to the active policy:

- FIFO preserves arrival order.
- SFF prioritizes the smallest file currently waiting in the queue.

The benchmark scripts are designed to compare both policies under the same workload conditions. Each
experiment uses a fixed seed so that the request mix is reproducible across replicas.

The campaign covers three scenarios:

- Scenario A: homogeneous workload with only small files.
- Scenario B: heterogeneous workload with 70% small files and 30% large files.
- Scenario C: stress workload with a much higher request rate.

For each scenario, the script executes 50 replicas under FIFO and 50 replicas under SFF.
Each replica produces a raw per-request CSV file plus one aggregated row in `summary.csv`.

## Experiment Workflow

The normal execution flow is:

1. Compile the server in `WebServer/`.
2. Generate the document root in `DataAnalysis/` with `setup_files.sh`.
3. Run `run_experiments.sh` from `DataAnalysis/` to launch the server, execute the client, and collect results.
4. Run `analyze_results.py results/summary.csv` from `DataAnalysis/` to analyze the measurements.

On Linux, the workflow can be executed with the following commands:

```bash

# 1) Prepare the document root
bash setup_files.sh www

# 2) Build the concurrent web server
make clean
make

# 3) Run the full experiment campaign
bash run_experiments.sh

# 4) Analyze the collected data
python3 analyze_results.py results/summary.csv

# 5) Review the generated figures and tables
ls results/
```

The experiment runner stores:

- `raw_<scenario>_<policy>_<replica>.csv` for detailed request-level data.
- `summary.csv` for aggregated metrics per replica.

## Data Analysis

The analysis script reads `results/summary.csv` and compares FIFO vs SFF for each scenario and metric.
It computes descriptive statistics for each group:

- Mean
- Standard deviation
- Median
- p95
- p99
- Coefficient of variation (CV), used as a fairness indicator

It also applies statistical tests:

- Shapiro-Wilk normality test to check whether the samples look normal.
- Mann-Whitney U test to compare FIFO and SFF without assuming normality.
- Rank-biserial effect size to estimate how strong the difference is.

The script generates visual outputs in `results/`:

- Boxplots for latency and throughput.
- Violin plots for the distributions.
- `analysis_summary.csv` with the computed statistics.
- `summary_table.png` as a compact visual summary.

### How to interpret the analysis

- Lower latency means faster request service.
- Higher throughput means the server processed more requests per second.
- A lower CV suggests more stable behavior across replicas.
- If the Mann-Whitney U test returns a p-value below 0.05, the difference between FIFO and SFF is
  considered statistically significant for that scenario and metric.

## Key Files

- `WebServer/wserver.c` controls the server concurrency model.
- `WebServer/buffer.c` implements the policy-dependent queue selection.
- `DataAnalysis/load_client.py` generates reproducible workloads and writes the CSV outputs.
- `DataAnalysis/run_experiments.sh` orchestrates the benchmark campaign.
- `DataAnalysis/analyze_results.py` turns raw results into statistics and plots.

## Notes

- The project assumes `python3`, `pandas`, `scipy`, `matplotlib`, and `seaborn` are available for the
  analysis stage.
- The default port used by the experiment script is `10000`.
- The generated results can be large because the full campaign runs 3 scenarios x 2 policies x 50 replicas.

## Conclusion

The original server code is preserved in the folder `CodeBase/` of the workspace, while `Solution/` contains the completed implementation, the automation scripts, and the statistical analysis workflow used to compare FIFO and SFF under controlled experimental conditions.
