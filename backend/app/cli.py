"""Command-line interface for Cronos backend administration tasks.

Run with ``uv run python -m app.cli <command> --help`` from the backend
directory. The first administrator is provisioned out-of-band through
``seed-admin`` because account creation over the API is admin-only (see
design.md decision D6).
"""

import argparse
import getpass
import os
import sys

from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve the admin username and password from flags, env, or prompts.

    Precedence for each value: explicit CLI flag, then the corresponding
    ``CRONOS_ADMIN_*`` environment variable, then an interactive prompt.

    @param args Parsed arguments (may carry ``--username``/``--password``).
    @return A ``(username, password)`` pair ready to be persisted.
    @raises SystemExit 2 when a value ends up empty.
    """
    username = args.username or os.environ.get("CRONOS_ADMIN_USERNAME")
    if not username:
        username = input("Admin username: ").strip()
    password = args.password or os.environ.get("CRONOS_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Admin password: ")

    if not username or not password:
        print("error: username and password must be non-empty", file=sys.stderr)
        raise SystemExit(2)
    return username, password


def seed_admin(args: argparse.Namespace) -> int:
    """Create the first administrator account.

    The command refuses to run when a user with the given username already
    exists, so it can never overwrite an existing account.

    @param args Parsed arguments for the ``seed-admin`` subcommand.
    @return Process exit code: 0 on success, 1 when the user already exists.
    """
    username, password = _resolve_credentials(args)

    with SessionLocal() as session:
        existing = session.query(User).filter(User.username == username).first()
        if existing is not None:
            print(
                f"error: user '{username}' already exists; "
                "refusing to overwrite it",
                file=sys.stderr,
            )
            return 1

        user = User(
            username=username,
            password_hash=hash_password(password),
            is_admin=True,
        )
        session.add(user)
        session.commit()

    print(f"Admin user '{username}' created.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the selected subcommand.

    @param argv Argument vector (defaults to ``sys.argv[1:]``).
    @return The process exit code for the executed command.
    """
    parser = argparse.ArgumentParser(
        prog="cronos", description="Cronos backend administration CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser(
        "seed-admin", help="Create the first administrator account"
    )
    seed.add_argument(
        "--username",
        help="Admin username (default: $CRONOS_ADMIN_USERNAME, then prompt)",
    )
    seed.add_argument(
        "--password",
        help="Admin password (default: $CRONOS_ADMIN_PASSWORD, then prompt)",
    )
    seed.set_defaults(func=seed_admin)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
