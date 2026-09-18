"""Read orders from SQLite with parameterized queries."""

import sqlite3

ORDER_COLUMNS = "id, customer_id, total_cents, status"


def orders_for_customer(
    conn: sqlite3.Connection, customer_id: int, status: str
) -> list[tuple[int, int, int, str]]:
    """A customer's orders with the given status, newest first."""
    return conn.execute(
        f"SELECT {ORDER_COLUMNS} FROM orders "
        "WHERE customer_id = ? AND status = ? ORDER BY id DESC",
        (customer_id, status),
    ).fetchall()


def cancel_order(conn: sqlite3.Connection, order_id: int) -> bool:
    """Cancel an open order; False if it was not open."""
    cursor = conn.execute(
        "UPDATE orders SET status = 'cancelled' "
        "WHERE id = ? AND status = 'open'",
        (order_id,),
    )
    conn.commit()
    return cursor.rowcount == 1
