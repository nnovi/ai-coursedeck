"""CourseDeck extraction benchmark: one command to run and score the experiment matrix.

    python main.py                 # run missing API experiments, score everything
    python main.py --local         # also run missing local (Ollama) experiments
    python main.py --score-only    # only recompute metrics from results/runs/
    python main.py --only NAME ... # a subset; --force reruns even if results exist
    python main.py --dry-run       # show what would run

Experiments are defined in configs/experiments.toml. Results are reused when
results/runs/<name>/summary.json exists, so re-running is free; the comparison table is
written to results/comparison.md.
"""

import argparse
import os
import shutil
import sys
import tomllib
from pathlib import Path

import httpx
from dotenv import load_dotenv

from coursedeck.dataset.manifest import read_manifest
from coursedeck.eval.score import GOLDEN_MANIFEST, load_golden, score_run, table
from coursedeck.extract.run import RUNS_DIR, RunConfig, run_experiment
from coursedeck.llm.models import MODELS, Sampling

CONFIG = Path("configs/experiments.toml")
COMPARISON = Path("results/comparison.md")
CREDENTIALS = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def load_experiments(path: Path) -> list[RunConfig]:
    data = tomllib.loads(path.read_text("utf-8"))
    defaults = data.get("defaults", {})
    out = []
    for exp in data["experiments"]:
        merged = {**defaults, **exp}
        out.append(RunConfig(
            name=merged["name"], model=merged["model"], mode=merged["mode"],
            prompt=merged.get("prompt", "v3"), sampling=Sampling(**merged.get("sampling", {})),
            manifest=Path(merged["manifest"]), timeout_s=merged.get("timeout_s", 120.0),
            max_retries=merged.get("max_retries", 2), workers=merged.get("workers"),
        ))
    names = [e.name for e in out]
    if len(names) != len(set(names)):
        sys.exit("experiment names in the config must be unique")
    return out


def ollama_available() -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        return httpx.get(f"{host}/api/tags", timeout=3).is_success
    except httpx.HTTPError:
        return False


def why_not_runnable(exp: RunConfig, local: bool) -> str | None:
    provider = MODELS[exp.model].provider
    if provider == "ollama":
        if not local:
            return "local model; pass --local"
        if not ollama_available():
            return "Ollama is not running"
    elif not os.environ.get(CREDENTIALS[provider]):
        return f"{CREDENTIALS[provider]} is not set (see .env.example)"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--only", nargs="*", help="experiment names to consider")
    ap.add_argument("--local", action="store_true", help="also run local Ollama experiments")
    ap.add_argument("--force", action="store_true", help="rerun experiments with results")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()

    experiments = load_experiments(args.config)
    if args.only:
        experiments = [e for e in experiments if e.name in set(args.only)]

    if not args.score_only:
        for exp in experiments:
            done = (RUNS_DIR / exp.name / "summary.json").exists()
            if done and not args.force:
                print(f"= {exp.name}: cached")
                continue
            reason = why_not_runnable(exp, args.local)
            if reason:
                print(f"- {exp.name}: skipped ({reason})")
                continue
            print(f"> {exp.name}: {exp.model} | {exp.mode} | {exp.prompt} | "
                  f"{exp.sampling.label()}")
            if args.dry_run:
                continue
            if (RUNS_DIR / exp.name).exists():
                shutil.rmtree(RUNS_DIR / exp.name)  # incomplete or forced rerun
            run_experiment(exp)

    golden = load_golden(include_drafts=False)
    rows = {r.doc_id: r for r in read_manifest(GOLDEN_MANIFEST)}
    scored = [score_run(RUNS_DIR / e.name, golden, rows) for e in experiments
              if (RUNS_DIR / e.name / "summary.json").exists()]
    if not scored:
        sys.exit("no results to score")
    md = (f"Golden set: {len(golden)} reviewed cards. Quality columns are measured on the "
          f"golden documents of each run; valid rate, latency and cost on all its documents."
          f"\n\n{table(scored)}\n")
    COMPARISON.parent.mkdir(parents=True, exist_ok=True)
    COMPARISON.write_text(md, "utf-8", newline="\n")
    print()
    print(md)
    print(f"written to {COMPARISON}")


if __name__ == "__main__":
    main()
