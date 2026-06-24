"""Entry point: `python -m webapp` launches the dashboard server."""

import argparse
import os
import sys

# When launched with pythonw.exe (used for hidden auto-start at logon) there is
# no console, so sys.stdout / sys.stderr are None. uvicorn's logger writes to
# stderr and would crash on startup. Redirect both to a log file first.
if sys.stdout is None or sys.stderr is None:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _log = open(os.path.join(_root, "dashboard.log"), "a", buffering=1, encoding="utf-8")
    sys.stdout = _log
    sys.stderr = _log

import uvicorn  # noqa: E402  (imported after the stdout fix above)


def main():
    parser = argparse.ArgumentParser(description="Camera Alert web dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="dev auto-reload")
    args = parser.parse_args()

    print(f"\n  Camera Alert dashboard -> http://{args.host}:{args.port}\n")
    uvicorn.run("webapp.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
