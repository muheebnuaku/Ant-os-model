"""Operator commands.

    uv run python -m antos_api.cli bootstrap
    uv run python -m antos_api.cli create-api-key --name ops --roles administrator [--nation GH]
    uv run python -m antos_api.cli generate-anchor-key DIR
    uv run python -m antos_api.cli anchor
    uv run python -m antos_api.cli verify-chain
    uv run python -m antos_api.cli replay-all
    uv run python -m antos_api.cli sweep-sla
    uv run python -m antos_api.cli deliver-notifications
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from antos_api import anchor, audit, demo, notify, service
from antos_api.app import build_notifier, build_runtime
from antos_api.auth import new_api_key
from antos_api.settings import Settings
from antos_api.tables import ApiKey


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antos_api.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="activate the on-disk profile if none is active")
    key = sub.add_parser("create-api-key", help="create an API key (prints the token once)")
    key.add_argument("--name", required=True)
    key.add_argument("--roles", nargs="+", required=True)
    key.add_argument("--nation")
    gen = sub.add_parser("generate-anchor-key", help="write a new Ed25519 key pair")
    gen.add_argument("directory", type=Path)
    sub.add_parser("anchor", help="sign the current head of the audit chain")
    sub.add_parser("verify-chain", help="recompute the audit chain and check anchors")
    sub.add_parser("replay-all", help="replay every recorded decision")
    sub.add_parser("sweep-sla", help="mark escalations past their SLA as breached")
    sub.add_parser("deliver-notifications", help="send pending notifications now")
    sub.add_parser("seed-demo", help="record sample decisions for a demonstration node")
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, default=str))


async def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate-anchor-key":
        private, public = anchor.generate_key_pair(args.directory)
        print(f"private key: {private}\npublic key:  {public}\n"
              "Set ANTOS_ANCHOR_PRIVATE_KEY_PATH, and give the public key to whoever "
              "holds copies of the anchors.")
        return 0

    settings = Settings()
    engine = create_async_engine(settings.database_url)
    rt = build_runtime(settings, async_sessionmaker(engine, expire_on_commit=False))
    try:
        if args.command == "bootstrap":
            async with rt.sessions.begin() as session:
                print(await service.bootstrap(session, rt.configs, settings.profile_dir))
        elif args.command == "create-api-key":
            roles = rt.rbac.known_roles(args.roles)
            key_id, secret_hash, token = new_api_key()
            async with rt.sessions.begin() as session:
                session.add(ApiKey(key_id=key_id, secret_hash=secret_hash, name=args.name,
                                   roles=roles, nation_id=args.nation, created_by="cli"))
                await session.flush()
                await audit.append(session, "api_key.created", key_id, "cli",
                                   {"key_id": key_id, "name": args.name, "roles": roles,
                                    "nation_id": args.nation})
            print(token)
        elif args.command == "anchor":
            if rt.anchor_signer is None:
                print("set ANTOS_ANCHOR_PRIVATE_KEY_PATH first", file=sys.stderr)
                return 2
            async with rt.sessions.begin() as session:
                row = await anchor.create_anchor(session, rt.anchor_signer, rt.node_id,
                                                 rt.clock())
            print(row.anchor_id if row else "nothing new to anchor")
        elif args.command == "verify-chain":
            async with rt.sessions() as session:
                chain = await audit.verify_chain(session)
                anchors = await anchor.verify_anchors(session, rt.anchor_keys)
            _print({"chain": chain.model_dump(), "anchors": anchors.model_dump()})
            return 0 if chain.ok and anchors.ok else 1
        elif args.command == "replay-all":
            report = await service.replay_all(rt, recorded_by="cli")
            _print({"ok": report.ok, **report.model_dump()})
            return 0 if report.ok else 1
        elif args.command == "sweep-sla":
            _print(await service.sweep_sla(rt))
        elif args.command == "deliver-notifications":
            delivery = await notify.deliver_pending(rt.sessions, build_notifier(settings),
                                                    rt.clock())
            _print(delivery.model_dump())
        elif args.command == "seed-demo":
            async with rt.sessions.begin() as session:
                await service.bootstrap(session, rt.configs, settings.profile_dir)
            _print(await demo.seed(rt))
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
