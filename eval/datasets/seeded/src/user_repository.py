"""Look up and page through user accounts stored in SQLite."""

import sqlite3
from dataclasses import dataclass

PAGE_SIZE = 20


@dataclass(frozen=True)
class User:
    """One row of the users table."""

    id: int
    email: str
    display_name: str


def find_by_email(conn: sqlite3.Connection, email: str) -> User | None:
    """Return the user with this email address, if any."""
    query = (
        "SELECT id, email, display_name FROM users "
        f"WHERE email = '{email}'"
    )
    row = conn.execute(query).fetchone()
    return User(*row) if row else None


def list_page(conn: sqlite3.Connection, page: int) -> list[User]:
    """Return one page of users ordered by id; the first page is 1."""
    offset = page * PAGE_SIZE
    rows = conn.execute(
        "SELECT id, email, display_name FROM users "
        "ORDER BY id LIMIT ? OFFSET ?",
        (PAGE_SIZE, offset),
    ).fetchall()
    return [User(*row) for row in rows]


def rename(conn: sqlite3.Connection, user_id: int, name: str) -> None:
    """Change a user's display name."""
    conn.execute(
        "UPDATE users SET display_name = ? WHERE id = ?", (name, user_id)
    )
    conn.commit()
