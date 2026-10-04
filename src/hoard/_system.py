from __future__ import annotations

import sqlite3
import subprocess

SYSTEM_VERBS = {
    "open": (("open",), "Opened"),
    "reveal": (("open", "-R"), "Revealed"),
}


def targets(con: sqlite3.Connection, ids) -> list:
    sql = """
        SELECT e.title,
               (SELECT s.locator FROM sightings s WHERE s.id = e.id ORDER BY s.mtime DESC LIMIT 1)
        FROM entities e WHERE e.id = ?
    """
    found = (con.execute(sql, (entity_id,)).fetchone() for entity_id in ids)
    return [row for row in found if row and row[1]]


def report(past: str, verb: str, titles: list) -> str:
    if not titles:
        return f"Nothing to {verb}"
    if len(titles) == 1:
        return f"{past} {titles[0]}"
    return f"{past} {len(titles)} items"


def hand_over(con: sqlite3.Connection, verb: str, ids) -> str:
    command, past = SYSTEM_VERBS[verb]
    found = targets(con, ids)
    for _, locator in found:
        subprocess.run([*command, locator], check=False)
    return report(past, verb, [title for title, _ in found])
