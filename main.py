"""One-command entry point, as the brief asks for:

    python main.py --bid ./data/bids/Bid1          # extraction mode: writes outputs/Bid1.json
    python main.py --question "When is Bid1 due?"  # question-answering mode
    python main.py --serve                         # REST API and web app on :8000

It is a thin wrapper over the `rfp` CLI (`uv run rfp --help` lists every command).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rfp_intel.cli import app


def main() -> None:
    parser = argparse.ArgumentParser(description="RFP Intelligence Platform")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bid", help="bid folder to extract (any path, or a name under data/bids)")
    mode.add_argument("--question", help="question to answer with citations")
    mode.add_argument("--serve", action="store_true", help="start the API and web app")
    parser.add_argument("--bid-id", help="restrict a question to one bid")
    parser.add_argument("--host", default="127.0.0.1", help="interface to serve on")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.bid:
        argv = ["extract", args.bid]
    elif args.question:
        argv = ["ask", args.question, *(["--bid", args.bid_id] if args.bid_id else [])]
    else:
        argv = ["serve", "--host", args.host, "--port", str(args.port)]
    app(argv)


if __name__ == "__main__":
    main()
