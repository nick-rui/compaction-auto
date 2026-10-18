"""Run a grid of compaction configurations with `inspect eval-set`.

    python scripts/run_grid.py configs/example_grid.yaml

Grid file:
    log_dir: runs/my_experiment
    model: openai-api/local/qwen3.8-27b
    epochs: 3
    max_samples: 16              # concurrent samples (sandboxes) across the grid
    common: {scenarios: scenarios/smoke, window: 120000}
    grid:                        # cartesian product of these task parameters
      harness: [claude_code, codex_cli]
      policy: [harness_default, every_10, honest_pre]
"""

import itertools
import subprocess
import sys

import yaml


def main(path: str) -> None:
    cfg = yaml.safe_load(open(path))
    grid = cfg.get("grid", {})
    keys = list(grid)
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*grid.values())] or [{}]
    for combo in combos:
        params = {**cfg.get("common", {}), **combo}
        cmd = ["inspect", "eval", "ce/tasks.py@compaction_eval", "--model", cfg["model"],
               "--log-dir", cfg["log_dir"], "--epochs", str(cfg.get("epochs", 1)),
               "--max-samples", str(cfg.get("max_samples", 8)), "--no-ansi", "--display", "plain"]
        for k, v in params.items():
            cmd += ["-T", f"{k}={v}"]
        print("+", " ".join(cmd), flush=True)
        subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main(sys.argv[1])
