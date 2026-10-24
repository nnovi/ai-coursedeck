"""Run extraction over a manifest and record cards, usage, cost and latency.

    python -m coursedeck.extract.run --model haiku --mode text --prompt v3 --effort medium
    python -m coursedeck.extract.run --model qwen3-vl-8b --mode image --temperature 0 --top-p 0.9

Writes results/runs/<run_id>/: config.json (model, prompt version and hash, sampling, git
commit), one <doc_id>.json per document (card, attempts, tokens, cost, latency) and
summary.json. Experiment matrices live in configs/ and run through main.py.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from coursedeck.dataset.manifest import ManifestRow, read_manifest
from coursedeck.extract.extractor import MODES, build_input, extract
from coursedeck.llm.models import MODELS, ModelSpec, Sampling, make_adapter
from coursedeck.prompts import load_prompt, prompt_hash

RUNS_DIR = Path("results/runs")
GOLDEN_MANIFEST = Path("data/manifests/golden.csv")


@dataclass
class RunConfig:
    name: str
    model: str
    mode: str
    prompt: str = "v3"
    sampling: Sampling = field(default_factory=Sampling)
    manifest: Path = GOLDEN_MANIFEST
    docs: list[str] | None = None
    limit: int | None = None
    workers: int | None = None
    file_name: bool | None = None  # send the source file name; None = on for prompt v3+
    timeout_s: float = 120.0
    max_retries: int = 2  # transport retries (HTTP 429/5xx, timeouts)

    @property
    def send_file_name(self) -> bool:
        return self.file_name if self.file_name is not None else int(self.prompt[1:]) >= 3


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_doc(row: ManifestRow, spec: ModelSpec, adapter, system: str, mode: str,
            send_file_name: bool) -> dict:
    doc = build_input(row.path, mode, row.source_file if send_file_name else None)
    try:
        ex = extract(adapter, system, doc)
    except Exception as e:  # noqa: BLE001 - API/network failures are results too
        return {"doc_id": row.doc_id, "ok": False, "status": "failed",
                "error": f"{type(e).__name__}: {e}", "card": None, "attempts": [],
                "n_pages": doc.n_pages}
    billed = [a.billed_cost_usd for a in ex.attempts]
    return {
        "doc_id": row.doc_id,
        "ok": ex.card is not None,
        "status": "ok" if ex.card else "failed",
        "error": ex.error,
        "card": ex.card.model_dump(mode="json") if ex.card else None,
        "n_attempts": len(ex.attempts),
        "first_attempt_valid": bool(ex.attempts) and ex.attempts[0].error is None,
        "usage": asdict(ex.usage),
        "cost_usd": spec.cost(ex.usage),
        "billed_cost_usd": sum(billed) if billed and None not in billed else None,
        "latency_s": ex.latency_s,
        "n_pages": doc.n_pages,
        "image_pixels": doc.image_pixels,
        "attempts": ex.attempts_json(),
    }


def percentile(values: list[float], q: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if r["ok"]]
    lat = [r["latency_s"] for r in results if r.get("latency_s")]
    cost = sum(r.get("cost_usd", 0) for r in results)
    n = len(results)
    return {
        "n_docs": n,
        "valid": len(ok),
        "valid_rate": len(ok) / n if n else None,
        "first_attempt_valid_rate": (sum(r.get("first_attempt_valid", False) for r in results)
                                     / n if n else None),
        "retried": sum(r.get("n_attempts", 0) > 1 for r in results),
        "errors": {r["doc_id"]: r["error"] for r in results if not r["ok"]},
        "latency_p50_s": percentile(lat, 50),
        "latency_p95_s": percentile(lat, 95),
        "cost_usd": cost,
        "cost_per_1000_docs_usd": cost / n * 1000 if n else None,
        "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0) for r in results),
        "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0) for r in results),
    }


def run_experiment(cfg: RunConfig, runs_dir: Path = RUNS_DIR, verbose: bool = True) -> Path:
    """Run one configuration; returns its run directory."""
    spec = MODELS[cfg.model]
    if cfg.mode == "pdf" and spec.provider != "anthropic":
        raise ValueError("pdf mode needs a provider with native PDF input (anthropic)")
    adapter = make_adapter(spec, cfg.sampling, cfg.timeout_s, cfg.max_retries)
    system = load_prompt("extract", cfg.prompt)

    rows = read_manifest(cfg.manifest)
    if cfg.docs:
        rows = [r for r in rows if r.doc_id in set(cfg.docs)]
    rows = rows[: cfg.limit]
    missing = [r.doc_id for r in rows if not r.path.exists()]
    if missing:
        raise FileNotFoundError(f"missing PDFs (run coursedeck.dataset.fetch): {missing[:5]}")

    out = runs_dir / cfg.name
    out.mkdir(parents=True, exist_ok=False)
    config = {
        "run_id": cfg.name, "model": spec.alias, "model_id": spec.model_id,
        "provider": spec.provider, "mode": cfg.mode, "prompt": cfg.prompt,
        "prompt_sha": prompt_hash(system), **asdict(cfg.sampling),
        "file_name_hint": cfg.send_file_name, "timeout_s": cfg.timeout_s,
        "max_retries": cfg.max_retries, "manifest": str(cfg.manifest),
        "doc_ids": [r.doc_id for r in rows], "git_commit": git_commit(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2), "utf-8", newline="\n")

    def work(row: ManifestRow) -> dict:
        res = run_doc(row, spec, adapter, system, cfg.mode, cfg.send_file_name)
        (out / f"{row.doc_id}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), "utf-8", newline="\n")
        return res

    workers = cfg.workers or (1 if spec.provider == "ollama" else 4)
    results = []
    with ThreadPoolExecutor(workers) as pool:
        for i, res in enumerate(pool.map(work, rows), 1):
            results.append(res)
            if verbose:
                status = "ok" if res["ok"] else f"FAILED: {res['error']}"
                print(f"  [{i}/{len(rows)}] {res['doc_id']}: {status} "
                      f"({res.get('latency_s', 0):.1f}s, ${res.get('cost_usd', 0):.4f})")

    (out / "summary.json").write_text(json.dumps(summarize(results), indent=2), "utf-8",
                                      newline="\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--prompt", default="v3", help="prompt version in prompts/extract/")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Anthropic models only")
    ap.add_argument("--temperature", type=float, help="Ollama/OpenRouter models")
    ap.add_argument("--top-p", type=float, help="Ollama/OpenRouter models")
    ap.add_argument("--manifest", type=Path, default=GOLDEN_MANIFEST)
    ap.add_argument("--docs", nargs="*", help="only these doc ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, help="parallel requests (default: 4 API, 1 local)")
    ap.add_argument("--timeout", type=float, default=120.0, help="request timeout, seconds")
    ap.add_argument("--name", help="run id (default: timestamp_model_mode_prompt)")
    ap.add_argument("--file-name", action=argparse.BooleanOptionalAction,
                    help="send the source file name (default: on for prompt v3 and later)")
    args = ap.parse_args()

    load_dotenv()
    name = args.name or (f"{time.strftime('%Y%m%d-%H%M%S')}_{args.model}_"
                         f"{args.mode.replace('+', '-')}_{args.prompt}")
    cfg = RunConfig(
        name=name, model=args.model, mode=args.mode, prompt=args.prompt,
        sampling=Sampling(args.effort, args.temperature, args.top_p),
        manifest=args.manifest, docs=args.docs, limit=args.limit, workers=args.workers,
        file_name=args.file_name, timeout_s=args.timeout,
    )
    try:
        out = run_experiment(cfg)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(str(e))
    summary = json.loads((out / "summary.json").read_text("utf-8"))
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=2))
    print(f"run saved to {out}")


if __name__ == "__main__":
    main()
