import sqlite3

import config


def get_connection() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(config.SCHEMA_PATH.read_text())
        for pkg in config.PACKAGES:
            conn.execute(
                "INSERT OR IGNORE INTO packages (slug, display_name) VALUES (?, ?)",
                (pkg["slug"], pkg["display_name"]),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {config.DB_PATH}")
