"""Command-line entry point for the ConstellaLab core.

Usage:
    python -m constellab_core status [--config PATH]
    python -m constellab_core validate PATH
    python -m constellab_core snapshot [PATH]
    python -m constellab_core serve [--host HOST] [--port PORT] [--scenario PATH]

PATH may be a scenario JSON file or a built-in scenario name
(``empty``, ``visual-orbit-demo``).

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
from .config import BUILTIN_SCENARIOS, DEFAULT_SCENARIO, ConfigError, load_config_file
from .orbit import initial_snapshot
from .service import serve, status_payload


def _print_errors(exc: ConfigError) -> int:
    print(json.dumps({"valid": False, "errors": exc.errors}, indent=2), file=sys.stderr)
    return 2


def _cmd_status(args: argparse.Namespace) -> int:
    if args.config:
        try:
            load_config_file(args.config)
        except ConfigError as exc:
            return _print_errors(exc)
    print(json.dumps(status_payload(), indent=2))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        config = load_config_file(args.path)
    except ConfigError as exc:
        return _print_errors(exc)
    print(json.dumps({"valid": True, "effective_config": config.to_dict()}, indent=2))
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    try:
        config = load_config_file(args.path)
    except ConfigError as exc:
        return _print_errors(exc)
    print(initial_snapshot(config).to_json(indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        scenario = load_config_file(args.scenario)
    except ConfigError as exc:
        return _print_errors(exc)
    server = serve(args.host, args.port, scenario)
    actual = server.server_address
    print(f"constellab-core {__version__} listening on http://{actual[0]}:{actual[1]} "
          f"(scenario {scenario.scenario_id}, {len(scenario.satellites)} satellites)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    builtin = ", ".join(BUILTIN_SCENARIOS)
    parser = argparse.ArgumentParser(prog="constellab_core", description="ConstellaLab simulation core")
    parser.add_argument("--version", action="version", version=f"constellab-core {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="print the version/status payload as JSON")
    p_status.add_argument("--config", metavar="PATH", help="validate a scenario file first")
    p_status.set_defaults(func=_cmd_status)

    p_validate = sub.add_parser("validate", help="validate a scenario file and print the effective config")
    p_validate.add_argument("path", metavar="PATH", help=f"scenario JSON file or built-in name ({builtin})")
    p_validate.set_defaults(func=_cmd_validate)

    p_snapshot = sub.add_parser("snapshot", help="print the epoch snapshot of a scenario")
    p_snapshot.add_argument("path", metavar="PATH", nargs="?", default=DEFAULT_SCENARIO,
                            help=f"scenario JSON file or built-in name ({builtin})")
    p_snapshot.set_defaults(func=_cmd_snapshot)

    p_serve = sub.add_parser("serve", help="run the local core HTTP service")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=0)
    p_serve.add_argument("--scenario", metavar="PATH", default=DEFAULT_SCENARIO,
                         help=f"scenario served by /api/snapshot ({builtin})")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
