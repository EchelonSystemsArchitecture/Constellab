"""Command-line entry point for the ConstellaLab core.

Usage:
    python -m constellab_core status [--config PATH]
    python -m constellab_core serve [--host HOST] [--port PORT]

Exit codes:
    0  success
    2  invalid configuration
    3  usage error
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import ConfigError
from .service import serve, status_payload


def _cmd_status(args: argparse.Namespace) -> int:
    if args.config:
        try:
            with open(args.config, "rb") as fh:
                raw = fh.read()
            from .config import validate_config_bytes
            validate_config_bytes(raw)
        except ConfigError as exc:
            print(json.dumps({"valid": False, "errors": exc.errors}, indent=2), file=sys.stderr)
            return 2
        except OSError as exc:
            print(json.dumps({"valid": False, "errors": [{"path": "$", "message": str(exc)}]}, indent=2),
                  file=sys.stderr)
            return 2
    print(json.dumps(status_payload(), indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    server = serve(args.host, args.port)
    actual = server.server_address
    print(f"constellab-core {__version__} listening on http://{actual[0]}:{actual[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="constellab_core", description="ConstellaLab simulation core")
    parser.add_argument("--version", action="version", version=f"constellab-core {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="print the version/status payload as JSON")
    p_status.add_argument("--config", metavar="PATH", help="validate a scenario config file first")
    p_status.set_defaults(func=_cmd_status)

    p_serve = sub.add_parser("serve", help="run the local core HTTP service")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=0)
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
