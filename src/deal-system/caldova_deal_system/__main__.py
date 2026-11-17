"""Run the Deal System: python -m caldova_deal_system [--port 8080] [--reset]."""

from __future__ import annotations

import argparse

import uvicorn

from .app import create_app
from .config import Settings
from .store import JsonStore


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(prog="python -m caldova_deal_system", description="Caldova Deal System (fictional data)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.port, help="port (default DEAL_SYSTEM_PORT or 8080)")
    parser.add_argument("--reset", action="store_true", help="reset state to the seed and exit")
    args = parser.parse_args()
    settings.port = args.port

    if args.reset:
        store = JsonStore(settings.state_dir, settings.seed_path, reset=True)
        print(f"Deal System state reset from {settings.seed_path} ({store.read(lambda s: len(s['deals']))} deals).")
        return

    if not settings.api_key:
        print("WARNING: DEAL_SYSTEM_API_KEY is not set. The REST and MCP API is unauthenticated and answers only direct "
              "local requests. Set a key before exposing this server (for example through a dev tunnel).", flush=True)
    print(f"Deal System: dashboard {settings.local_url}/  MCP {settings.local_url}/mcp  state {settings.state_dir}", flush=True)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=False, log_level="info")


if __name__ == "__main__":
    main()
