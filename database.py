import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "packages.db")


def initialize_database():
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            tracking_number TEXT NOT NULL,
            carrier TEXT,
            status TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            public_responses INTEGER NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("""
        DELETE FROM packages
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM packages
            GROUP BY user_id, tracking_number
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_packages_user_tracking
        ON packages (user_id, tracking_number)
    """)

    connection.commit()
    connection.close()


def get_public_responses(user_id):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT public_responses
        FROM user_settings
        WHERE user_id = ?
    """, (user_id,))

    setting = cursor.fetchone()
    connection.close()

    return setting is None or bool(setting[0])


def set_public_responses(user_id, public):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO user_settings (user_id, public_responses)
        VALUES (?, ?)
        ON CONFLICT (user_id)
        DO UPDATE SET public_responses = excluded.public_responses
    """, (user_id, int(public)))

    connection.commit()
    connection.close()


def add_package(user_id, tracking_number, carrier, status):
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO packages
        (user_id, tracking_number, carrier, status)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, tracking_number)
        DO UPDATE SET carrier = excluded.carrier, status = excluded.status
    """, (
        user_id,
        tracking_number,
        carrier,
        status
    ))

    connection.commit()
    connection.close()


def get_packages(user_id):
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        SELECT tracking_number, carrier, status
        FROM packages
        WHERE user_id = ?
    """, (user_id,))

    packages = cursor.fetchall()

    connection.close()

    return packages


def get_tracked_packages():
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        SELECT packages.id, packages.user_id, packages.tracking_number, packages.status
        FROM packages
        JOIN (
            SELECT MAX(id) AS id
            FROM packages
            GROUP BY user_id, tracking_number
        ) latest ON packages.id = latest.id
    """)

    packages = cursor.fetchall()

    connection.close()

    return packages


def update_package_status(user_id, tracking_number, status):
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE packages
        SET status = ?
        WHERE user_id = ? AND tracking_number = ?
    """, (status, user_id, tracking_number))

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    return updated


def remove_package(user_id, tracking_number):
    connection = sqlite3.connect(DATABASE)

    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM packages
        WHERE user_id = ? AND tracking_number = ?
    """, (
        user_id,
        tracking_number
    ))

    removed = cursor.rowcount

    connection.commit()
    connection.close()

    return removed