import os
import time

import aiosqlite

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "packages.db")

MAX_ACTIVE_PACKAGES_PER_USER = 15
ARCHIVE_RETENTION_DAYS = 60

# Columns added after the original schema. Existing databases are migrated automatically.
_NEW_PACKAGE_COLUMNS = {
    "label": "TEXT",
    "paused": "INTEGER NOT NULL DEFAULT 0",
    "archived": "INTEGER NOT NULL DEFAULT 0",
    "last_changed": "INTEGER NOT NULL DEFAULT 0",
    "channel_id": "TEXT",
}
_NEW_SETTINGS_COLUMNS = {
    "notifications_enabled": "INTEGER NOT NULL DEFAULT 1",
    "show_location": "INTEGER NOT NULL DEFAULT 1",
}
_SETTING_NAMES = {"public_responses", "notifications_enabled", "show_location"}


async def _add_missing_columns(db, table, columns):
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        existing = {row[1] async for row in cursor}

    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


async def initialize_database():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tracking_number TEXT NOT NULL,
                carrier TEXT,
                status TEXT,
                label TEXT,
                paused INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                last_changed INTEGER NOT NULL DEFAULT 0,
                channel_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                public_responses INTEGER NOT NULL DEFAULT 1,
                notifications_enabled INTEGER NOT NULL DEFAULT 1,
                show_location INTEGER NOT NULL DEFAULT 1
            )
        """)

        await _add_missing_columns(db, "packages", _NEW_PACKAGE_COLUMNS)
        await _add_missing_columns(db, "user_settings", _NEW_SETTINGS_COLUMNS)

        # Remove legacy duplicates before the unique index is created.
        await db.execute("""
            DELETE FROM packages
            WHERE id NOT IN (
                SELECT MAX(id) FROM packages GROUP BY user_id, tracking_number
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_packages_user_tracking
            ON packages (user_id, tracking_number)
        """)
        await db.execute(
            "UPDATE packages SET last_changed = ? WHERE last_changed = 0",
            (int(time.time()),)
        )
        await db.commit()


# ---------- Settings ----------

async def get_settings(user_id):
    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute("""
            SELECT public_responses, notifications_enabled, show_location
            FROM user_settings WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return {
            "public_responses": True,
            "notifications_enabled": True,
            "show_location": True,
        }

    return {
        "public_responses": bool(row[0]),
        "notifications_enabled": bool(row[1]),
        "show_location": bool(row[2]),
    }


async def set_setting(user_id, name, value):
    if name not in _SETTING_NAMES:
        raise ValueError(f"Unknown setting: {name}")
    if isinstance(value, bool):
        value = int(value)

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO user_settings (user_id) VALUES (?)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id,))
        # `name` is validated against a whitelist above.
        await db.execute(
            f"UPDATE user_settings SET {name} = ? WHERE user_id = ?",
            (value, user_id)
        )
        await db.commit()


# ---------- Packages ----------

async def add_package(
    user_id, tracking_number, carrier, status, label=None, archived=False, channel_id=None
):
    """
    Returns (result, label) where result is "added", "updated" or "limit".
    Archived (e.g. already delivered) packages don't count toward the limit.
    channel_id is the server channel the package was tracked in (None for DMs).
    """
    now = int(time.time())

    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute("""
            SELECT archived FROM packages
            WHERE user_id = ? AND tracking_number = ?
        """, (user_id, tracking_number)) as cursor:
            existing = await cursor.fetchone()

        already_active = existing is not None and not existing[0]

        if not archived and not already_active:
            async with db.execute("""
                SELECT COUNT(*) FROM packages WHERE user_id = ? AND archived = 0
            """, (user_id,)) as cursor:
                (count,) = await cursor.fetchone()

            if count >= MAX_ACTIVE_PACKAGES_PER_USER:
                return "limit", None

        await db.execute("""
            INSERT INTO packages
                (user_id, tracking_number, carrier, status, label, archived, paused,
                 last_changed, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT (user_id, tracking_number)
            DO UPDATE SET
                carrier = excluded.carrier,
                status = excluded.status,
                label = COALESCE(excluded.label, packages.label),
                archived = excluded.archived,
                paused = 0,
                channel_id = excluded.channel_id,
                last_changed = CASE
                    WHEN packages.status IS NOT excluded.status
                         OR packages.archived != excluded.archived
                    THEN excluded.last_changed
                    ELSE packages.last_changed
                END
        """, (user_id, tracking_number, carrier, status, label, int(archived), now, channel_id))

        async with db.execute("""
            SELECT label FROM packages WHERE user_id = ? AND tracking_number = ?
        """, (user_id, tracking_number)) as cursor:
            row = await cursor.fetchone()

        await db.commit()

    return ("added" if existing is None else "updated"), row[0]


async def get_packages(user_id, include_archived=True):
    query = """
        SELECT tracking_number, carrier, status, label, paused, archived
        FROM packages
        WHERE user_id = ?
    """
    if not include_archived:
        query += " AND archived = 0"
    query += " ORDER BY archived, id"

    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, (user_id,)) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def get_package(user_id, tracking_number):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT tracking_number, carrier, status, label, paused, archived
            FROM packages WHERE user_id = ? AND tracking_number = ?
        """, (user_id, tracking_number)) as cursor:
            row = await cursor.fetchone()

    return dict(row) if row else None


async def get_active_subscriptions():
    """Every active, unpaused package along with its owner's notification settings."""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT p.user_id, p.tracking_number, p.status, p.label, p.last_changed,
                   p.channel_id,
                   COALESCE(s.notifications_enabled, 1) AS notifications_enabled,
                   COALESCE(s.public_responses, 1) AS public_responses
            FROM packages p
            LEFT JOIN user_settings s ON s.user_id = p.user_id
            WHERE p.archived = 0 AND p.paused = 0
        """) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def update_package_status(user_id, tracking_number, status, archived=False):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            UPDATE packages
            SET status = ?, archived = ?, last_changed = ?
            WHERE user_id = ? AND tracking_number = ?
        """, (status, int(archived), int(time.time()), user_id, tracking_number))
        await db.commit()
        return cursor.rowcount


async def archive_package(user_id, tracking_number):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            UPDATE packages SET archived = 1, last_changed = ?
            WHERE user_id = ? AND tracking_number = ?
        """, (int(time.time()), user_id, tracking_number))
        await db.commit()
        return cursor.rowcount


async def set_paused(user_id, tracking_number, paused):
    async with aiosqlite.connect(DATABASE) as db:
        if paused:
            cursor = await db.execute("""
                UPDATE packages SET paused = 1
                WHERE user_id = ? AND tracking_number = ? AND archived = 0
            """, (user_id, tracking_number))
        else:
            # Reset the inactivity clock so a resumed package isn't instantly marked stale.
            cursor = await db.execute("""
                UPDATE packages SET paused = 0, last_changed = ?
                WHERE user_id = ? AND tracking_number = ? AND archived = 0
            """, (int(time.time()), user_id, tracking_number))
        await db.commit()
        return cursor.rowcount


async def remove_package(user_id, tracking_number):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            DELETE FROM packages WHERE user_id = ? AND tracking_number = ?
        """, (user_id, tracking_number))
        await db.commit()
        return cursor.rowcount


async def prune_archived():
    cutoff = int(time.time()) - ARCHIVE_RETENTION_DAYS * 86400
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            DELETE FROM packages WHERE archived = 1 AND last_changed < ?
        """, (cutoff,))
        await db.commit()
        return cursor.rowcount