#!/usr/bin/env python3
"""디스크 큐 워커 엔트리포인트.

  python -m services.worker
  python -m services.worker --once
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser(description="Garment pipeline disk worker")
    parser.add_argument("--once", action="store_true", help="잡 하나(또는 없음)만 처리 후 종료")
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args()
    from services.worker_queue import worker_loop
    worker_loop(poll_seconds=args.poll, once=args.once)


if __name__ == "__main__":
    main()
