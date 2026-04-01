"""Create the initial admin user."""
from __future__ import annotations

import asyncio
import sys

from matcher.auth.security import hash_password
from matcher.db.engine import async_session_factory
from matcher.db.repos.user import UserRepo


async def main() -> None:
    username = input("Admin username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    password = input("Admin password: ").strip()
    if len(password) < 12:
        print("Password must be at least 12 characters.")
        sys.exit(1)
    if password.isdigit() or password.isalpha():
        print("Password must contain both letters and digits (or special characters).")
        sys.exit(1)

    full_name = input("Full name (optional): ").strip() or None

    async with async_session_factory() as session:
        repo = UserRepo(session)
        existing = await repo.get_by_username(username)
        if existing:
            print(f"User '{username}' already exists.")
            sys.exit(1)

        user = await repo.create_user(
            username=username,
            hashed_password=hash_password(password),
            full_name=full_name,
            role="admin",
        )
        await session.commit()
        print(f"Admin user '{user.username}' created (id={user.user_id}).")


if __name__ == "__main__":
    asyncio.run(main())
