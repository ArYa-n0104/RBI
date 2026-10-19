"""Command-line interface for gold-only benchmark evaluation."""
from __future__ import annotations
import argparse
import json
import sys
from .evaluate import audit, read_jsonl, score

def main(argv=None):
    parser=argparse.ArgumentParser(description="Audit or score the TAARR benchmark.")
    sub=parser.add_subparsers(dest="command",required=True)
    a=sub.add_parser("audit",help="summarize labels and split leakage")
    a.add_argument("benchmark")
    s=sub.add_parser("score",help="score predictions only against gold_verified items")
    s.add_argument("benchmark")
    s.add_argument("predictions")
    args=parser.parse_args(argv)
    try:
        items=read_jsonl(args.benchmark)
        result=audit(items) if args.command=="audit" else score(items,read_jsonl(args.predictions))
        print(json.dumps(result,indent=2))
        return 0
    except (OSError,ValueError,TypeError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
