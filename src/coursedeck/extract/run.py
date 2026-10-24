"""Run extraction over a manifest and record cards, usage, cost and latency.

    python -m coursedeck.extract.run --model haiku --mode text --prompt v2
    python -m coursedeck.extract.run --model qwen3-vl-8b --mode image --docs ocw-2-001-lec24

Writes runs/<run_id>/: config.json, one <doc_id>.json per document, summary.json.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from coursedeck.dataset.manifest import ManifestRow, read_manifest
from coursedeck.extract.extractor import MODES, build_input, extract
from coursedeck.llm.models import MODELS, ModelSpec, make_adapter
from coursedeck.prompts import load_prompt, prompt_hash

RUNS_DIR = Path("runs")
GOLDEN_MANIFEST = Path("data/manifests/golden.csv")


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_doc(row: ManifestRow, spec: ModelSpec, adapter, system: str, mode: str) -> dict:
    doc = build_input(row.path, mode)
    try:
        ex = extract(adapter, system, doc)
    except Exception as e:  # noqa: BLE001 - API/network failures are results too
        return {"doc_id": row.doc_id, "ok": False, "error": f"{type(e).__name__}: {e}",
                "card": None, "attempts": [], "n_pages": doc.n_pages}
    return {
        "doc_id": row.doc_id,
        "ok": ex.card is not None,
        "error": ex.error,
        "card": ex.card.model_dump(mode="json") if ex.card else None,
        "n_attempts": len(ex.attempts),
        "first_attempt_valid": bool(ex.attempts) and ex.attempts[0].error is None,
        "usage": asdict(ex.usage),
        "cost_usd": spec.cost(ex.usage),
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
    return {
        "n_docs": len(results),
        "valid": len(ok),
        "valid_rate": len(ok) / len(results) if results else None,
        "first_attempt_valid_rate": (sum(r.get("first_attempt_valid", False) for r in results)
                                     / len(results) if results else None),
        "retried": sum(r.get("n_attempts", 0) > 1 for r in results),
        "errors": {r["doc_id"]: r["error"] for r in results if not r["ok"]},
        "latency_p50_s": percentile(lat, 50),
        "latency_p95_s": percentile(lat, 95),
        "cost_usd": cost,
        "cost_per_1000_docs_usd": cost / len(results) * 1000 if results else None,
        "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0) for r in results),
        "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0) for r in results),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--prompt", default="v2", help="prompt version in prompts/extract/")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Anthropic models only")
    ap.add_argument("--temperature", type=float, help="Ollama models only")
    ap.add_argument("--manifest", type=Path, default=GOLDEN_MANIFEST)
    ap.add_argument("--docs", nargs="*", help="only these doc ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, help="parallel requests (default: 4 API, 1 local)")
    ap.add_argument("--name", help="run id (default: timestamp_model_mode_prompt)")
    args = ap.parse_args()

    load_dotenv()
    spec = MODELS[args.model]
    if args.mode == "pdf" and spec.provider != "anthropic":
        sys.exit("pdf mode needs a provider with native PDF input (anthropic)")
    adapter = make_adapter(spec, effort=args.effort, temperature=args.temperature)
    system = load_prompt("extract", args.prompt)

    rows = read_manifest(args.manifest)
    if args.docs:
        rows = [r for r in rows if r.doc_id in set(args.docs)]
    rows = rows[: args.limit]
    missing = [r.doc_id for r in rows if not r.path.exists()]
    if missing:
        sys.exit(f"missing PDFs (run coursedeck.dataset.fetch): {missing[:5]}")

    run_id = args.name or (f"{time.strftime('%Y%m%d-%H%M%S')}_{args.model}_"
                           f"{args.mode.replace('+', '-')}_{args.prompt}")
    out = RUNS_DIR / run_id
    out.mkdir(parents=True, exist_ok=False)
    config = {
        "run_id": run_id, "model": spec.alias, "model_id": spec.model_id,
        "provider": spec.provider, "mode": args.mode, "prompt": args.prompt,
        "prompt_sha": prompt_hash(system), "effort": args.effort,
        "temperature": args.temperature, "manifest": str(args.manifest),
        "doc_ids": [r.doc_id for r in rows], "git_commit": git_commit(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2), "utf-8")

    workers = args.workers or (4 if spec.provider == "anthropic" else 1)
    results = []

    def work(row: ManifestRow) -> dict:
        res = run_doc(row, spec, adapter, system, args.mode)
        (out / f"{row.doc_id}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), "utf-8")
        return res

    with ThreadPoolExecutor(workers) as pool:
        for i, res in enumerate(pool.map(work, rows), 1):
            results.append(res)
            status = "ok" if res["ok"] else f"FAILED: {res['error']}"
            print(f"[{i}/{len(rows)}] {res['doc_id']}: {status} "
                  f"({res.get('latency_s', 0):.1f}s, ${res.get('cost_usd', 0):.4f})")

    summary = summarize(results)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=2))
    print(f"run saved to {out}")


if __name__ == "__main__":
    main()
