"""Measure retrieval, and choose the refusal threshold with data.

Two things get measured, because they fail differently.

RETRIEVAL — given a question, does the right page appear in the top k?
  recall@k  fraction of answerable questions whose correct page is in the top k.
            This is the ceiling on answer quality: the answerer cannot use a
            passage it never received.
  MRR       1/rank of the first correct passage, averaged. Rewards putting the
            right passage first rather than fourth, which recall@k ignores.

REFUSAL — does it know when it doesn't know? The question set includes questions
the corpus genuinely cannot answer, and the sweep finds where answering and
declining balance. Any threshold looks good on one metric alone: set it to
infinity and refusal is perfect while nothing gets answered.

    python scripts/evaluate.py
    python scripts/evaluate.py --retriever hybrid --compare

Writes data/eval_results.json, which /maintainer/quality renders.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline import Bot  # noqa: E402


def evaluate_retrieval(bot, questions, k=5):
    answerable = [q for q in questions if q["expected_page"]]
    hits, rr, misses = 0, [], []
    for q in answerable:
        got = [p.page_id for p in bot.retrieve(q["question"], k=k).passages]
        if q["expected_page"] in got:
            hits += 1
            rr.append(1.0 / (got.index(q["expected_page"]) + 1))
        else:
            rr.append(0.0)
            misses.append({"question": q["question"], "expected": q["expected_page"],
                           "got": got[:2]})
    n = max(len(answerable), 1)
    return {"n_answerable": len(answerable), "recall": hits / n,
            "mrr": sum(rr) / n, "misses": misses}


def sweep_threshold(bot, questions, k=4, thresholds=None):
    """Score every question once, then test thresholds against those scores —
    retrieval is the expensive part, so it runs once per question."""
    thresholds = thresholds or [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]
    scored = [(q["expected_page"] is not None, bot.retrieve(q["question"], k=k).top_score)
              for q in questions]
    rows = []
    for t in thresholds:
        tp = sum(1 for ans, s in scored if ans and s >= t)
        fn = sum(1 for ans, s in scored if ans and s < t)
        fp = sum(1 for ans, s in scored if not ans and s >= t)
        tn = sum(1 for ans, s in scored if not ans and s < t)
        rows.append({"threshold": t, "answered_correctly": tp, "wrongly_declined": fn,
                     "wrongly_answered": fp, "declined_correctly": tn,
                     "accuracy": (tp + tn) / max(len(scored), 1)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(ROOT / "data" / "sources.json"))
    ap.add_argument("--questions", default=str(ROOT / "data" / "eval_questions.json"))
    ap.add_argument("--retriever", default="bm25", choices=["bm25", "dense", "hybrid"])
    ap.add_argument("--compare", action="store_true",
                    help="evaluate every retriever (dense needs sentence-transformers)")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "data" / "eval_results.json"))
    args = ap.parse_args()

    questions = json.loads(Path(args.questions).read_text())
    names = ["bm25", "dense", "hybrid"] if args.compare else [args.retriever]
    report, primary = {}, None

    for name in names:
        try:
            bot = Bot.from_path(args.sources, retriever=name, top_k=args.k)
        except ImportError as e:
            print(f"\n{name}: skipped ({e})")
            continue
        res = evaluate_retrieval(bot, questions, k=args.k)
        print(f"\nretriever = {name}")
        print(f"  questions   {res['n_answerable']}")
        print(f"  recall@{args.k}    {res['recall']:.1%}")
        print(f"  MRR         {res['mrr']:.3f}")
        for m in res["misses"][:5]:
            print(f"    missed {m['question']!r} — wanted {m['expected']}, got {m['got']}")
        report[name] = {kk: vv for kk, vv in res.items() if kk != "misses"}

        if primary is None:
            primary = (name, bot, res)

    if primary is None:
        sys.exit("no retriever could be evaluated")

    name, bot, res = primary
    sweep = sweep_threshold(bot, questions)
    best = max(sweep, key=lambda r: r["accuracy"])
    print("\n  refusal threshold sweep")
    print("  cut-off  answered  wrongly-declined  wrongly-answered  accuracy")
    for r in sweep:
        print(f"  {r['threshold']:7.1f}  {r['answered_correctly']:8d}  "
              f"{r['wrongly_declined']:16d}  {r['wrongly_answered']:16d}  {r['accuracy']:.1%}")
    print(f"\n  best cut-off on this set: {best['threshold']} "
          f"(accuracy {best['accuracy']:.1%})")

    out = {
        "retriever": name, "k": args.k,
        "recall": res["recall"], "mrr": res["mrr"],
        "misses": res["misses"][:8],
        "sweep": sweep,
        "chosen_threshold": best["threshold"],
        "abstention_accuracy": best["accuracy"],
        "all_retrievers": report,
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nwrote {args.out} — see /maintainer/quality")


if __name__ == "__main__":
    main()
