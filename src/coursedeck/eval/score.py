"""Score extraction runs against the golden set and compare them.

    python -m coursedeck.eval.score runs/<run_a> runs/<run_b> ... [--include-drafts]

Writes runs/<run>/scores.json and prints a comparison table (markdown), overall and by
document stratum (Ukrainian, English scans, slides, notes).
"""

import argparse
import json
import sys
from pathlib import Path

from coursedeck.dataset.manifest import ManifestRow, read_manifest
from coursedeck.eval.metrics import aggregate, score_card
from coursedeck.golden import store

GOLDEN_MANIFEST = Path("data/manifests/golden.csv")


def stratum(row: ManifestRow) -> str:
    if row.lang == "uk":
        return "uk"
    if row.text_layer == "none":
        return "en-scan"
    return "en-slides" if row.layout == "slides" else "en-notes"


def load_golden(include_drafts: bool) -> dict[str, dict]:
    golden = {}
    for path in sorted(store.GOLDEN_DIR.glob("*.json")):
        rec = json.loads(path.read_text("utf-8"))
        if rec["status"] == "reviewed" or include_drafts:
            golden[rec["doc_id"]] = rec["card"]
    return golden


def score_run(run_dir: Path, golden: dict[str, dict], rows: dict[str, ManifestRow]) -> dict:
    config = json.loads((run_dir / "config.json").read_text("utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text("utf-8"))
    per_doc = {}
    for doc_id in config["doc_ids"]:
        if doc_id not in golden:
            continue
        res = json.loads((run_dir / f"{doc_id}.json").read_text("utf-8"))
        per_doc[doc_id] = score_card(golden[doc_id], res["card"])
    by_stratum = {}
    for s in sorted({stratum(rows[d]) for d in per_doc}):
        by_stratum[s] = aggregate({d: v for d, v in per_doc.items() if stratum(rows[d]) == s})
    scores = {"config": config, "summary": summary, "overall": aggregate(per_doc),
              "by_stratum": by_stratum, "per_doc": per_doc}
    (run_dir / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2),
                                         "utf-8")
    return scores


def fmt(x, digits: int = 2) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def label(cfg: dict) -> str:
    sampling = (f"effort={cfg['effort']}" if cfg.get("effort") else
                f"t={cfg['temperature']}" if cfg.get("temperature") is not None else "default")
    return f"{cfg['model']} | {cfg['mode']} | {cfg['prompt']} | {sampling}"


def table(all_scores: list[dict]) -> str:
    lines = [
        ("| model | mode | prompt | sampling | valid | facts | halluc. | omitted | class. "
         "| content F1 | overall | p50 s | p95 s | $/1000 docs |"),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in all_scores:
        o, sm = s["overall"], s["summary"]
        lines.append(
            f"| {label(s['config'])} | {fmt(sm['valid_rate'])} | {fmt(o['groups']['fact'])} "
            f"| {fmt(o['hallucination_rate'])} | {fmt(o['omission_rate'])} "
            f"| {fmt(o['groups']['classification'])} | {fmt(o['groups']['content'])} "
            f"| {fmt(o['overall'])} | {fmt(sm['latency_p50_s'], 1)} | {fmt(sm['latency_p95_s'], 1)} "
            f"| {fmt(sm['cost_per_1000_docs_usd'])} |"
        )
    strata = sorted({k for s in all_scores for k in s["by_stratum"]})
    lines += ["", "Overall score by stratum:", "",
              "| model | mode | prompt | sampling | " + " | ".join(strata) + " |",
              "|---|---|---|---|" + "---|" * len(strata)]
    for s in all_scores:
        cells = [fmt(s["by_stratum"].get(k, {}).get("overall")) for k in strata]
        lines.append(f"| {label(s['config'])} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--include-drafts", action="store_true",
                    help="also use golden cards that are not reviewed yet")
    ap.add_argument("--out", type=Path, help="write the markdown table to this file")
    args = ap.parse_args()

    golden = load_golden(args.include_drafts)
    if not golden:
        sys.exit("no reviewed golden cards; review them or pass --include-drafts")
    rows = {r.doc_id: r for r in read_manifest(GOLDEN_MANIFEST)}
    all_scores = [score_run(r, golden, rows) for r in args.runs]
    md = table(all_scores)
    status = "draft + reviewed" if args.include_drafts else "reviewed"
    md = f"Golden: {len(golden)} cards ({status}).\n\n{md}"
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md + "\n", "utf-8")


if __name__ == "__main__":
    main()
