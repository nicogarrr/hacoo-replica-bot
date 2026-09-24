"""SQLite + FTS5: indice local de enlaces de la comunidad."""
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    channel TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    posted_at TEXT,
    title TEXT,
    raw_text TEXT,
    PRIMARY KEY (channel, message_id)
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    resolved_url TEXT,
    product_id TEXT,
    resolved_at REAL,
    UNIQUE (channel, message_id, url)
);
CREATE VIRTUAL TABLE IF NOT EXISTS links_fts USING fts5(
    title, content='links', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS links_ai AFTER INSERT ON links BEGIN
    INSERT INTO links_fts(rowid, title)
    SELECT new.id, (SELECT title FROM messages m
                    WHERE m.channel = new.channel AND m.message_id = new.message_id);
END;
CREATE TRIGGER IF NOT EXISTS links_ad AFTER DELETE ON links BEGIN
    INSERT INTO links_fts(links_fts, rowid, title) VALUES('delete', old.id, '');
END;
"""


class DB:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn = sqlite3.connect(path, timeout=30, isolation_level=None,
                                check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # autocommit: leer-then-escribir en una transaccion heredada da
        # SQLITE_BUSY_SNAPSHOT al instante con otro escritor en WAL.
        # WAL + busy_timeout: bot (resolver/crawler) y backfill conviven
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript(SCHEMA)
        for col in ("dead_at", "checked_at"):
            if col not in {r["name"] for r in
                           self.conn.execute("PRAGMA table_info(links)")}:
                self.conn.execute(f"ALTER TABLE links ADD COLUMN {col} REAL")

    def min_message_id(self, channel: str) -> int:
        row = self.conn.execute(
            "SELECT MIN(message_id) AS m FROM messages WHERE channel = ?", (channel,)
        ).fetchone()
        return row["m"] or 0

    def max_message_id(self, channel: str) -> int:
        row = self.conn.execute(
            "SELECT MAX(message_id) AS m FROM messages WHERE channel = ?", (channel,)
        ).fetchone()
        return row["m"] or 0

    def insert_message(self, channel: str, message_id: int, posted_at: str,
                       title: str, raw_text: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?)",
            (channel, message_id, posted_at, title, raw_text),
        )

    def insert_link(self, channel: str, message_id: int, url: str) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO links (channel, message_id, url) VALUES (?,?,?)",
            (channel, message_id, url),
        )
        return cur.lastrowid or 0

    def commit(self) -> None:
        self.conn.commit()

    def links_to_check(self, limit: int) -> list:
        """Enlaces para chequeo de vida: nunca chequeados primero."""
        return self.conn.execute(
            """
            SELECT id, url FROM links
            WHERE dead_at IS NULL
            ORDER BY checked_at IS NOT NULL, checked_at
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def mark_checked(self, link_id: int, dead: bool) -> None:
        if dead:
            self.conn.execute(
                "UPDATE links SET dead_at = ?, checked_at = ? WHERE id = ?",
                (time.time(), time.time(), link_id))
        else:
            self.conn.execute(
                "UPDATE links SET checked_at = ?, dead_at = NULL WHERE id = ?",
                (time.time(), link_id))

    def unresolved_links(self, limit: int) -> list:
        return self.conn.execute(
            "SELECT id, url FROM links WHERE resolved_at IS NULL ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()

    def mark_resolved(self, link_id: int, resolved_url: str, product_id: str) -> None:
        self.conn.execute(
            "UPDATE links SET resolved_url = ?, product_id = ?, resolved_at = ? WHERE id = ?",
            (resolved_url, product_id, time.time(), link_id),
        )

    def mark_failed(self, link_id: int) -> None:
        self.conn.execute(
            "UPDATE links SET resolved_at = ? WHERE id = ?", (time.time(), link_id)
        )

    def search_fts(self, query: str, limit: int = 8, mode: str = "and") -> list:
        terms = [t for t in query.split() if len(t) >= 2]
        if not terms:
            return []
        joiner = " OR " if mode == "or" else " AND "
        match = joiner.join(f'"{t}"*' for t in terms)
        return self.conn.execute(
            """
            SELECT l.id, m.title, m.posted_at, l.channel, l.message_id,
                   COALESCE(l.resolved_url, l.url) AS link, l.product_id,
                   bm25(links_fts) AS score
            FROM links_fts f
            JOIN links l ON l.id = f.rowid
            JOIN messages m ON m.channel = l.channel AND m.message_id = l.message_id
            WHERE links_fts MATCH ? AND l.dead_at IS NULL
            ORDER BY score, m.message_id DESC
            LIMIT ?
            """,
            (match, limit * 3),
        ).fetchall()

    def search_fts_with_any(self, tokens_and: list, any_terms: list,
                            limit: int = 8) -> list:
        """AND de tokens de marca/modelo + (OR de lexico de categoria).

        Garantiza que los titulos con tipo de producto ("Zapatillas RL
        Heritage") aparezcan aunque el top bm25 este lleno de titulos
        genericos de la marca.
        """
        ands = " AND ".join(f'"{t}"*' for t in tokens_and if len(t) >= 2)
        anys = " OR ".join(f'"{t}"*' for t in any_terms)
        if not ands or not anys:
            return []
        match = f"({ands}) AND ({anys})"
        return self.conn.execute(
            """
            SELECT l.id, m.title, m.posted_at, l.channel, l.message_id,
                   COALESCE(l.resolved_url, l.url) AS link, l.product_id,
                   bm25(links_fts) AS score
            FROM links_fts f
            JOIN links l ON l.id = f.rowid
            JOIN messages m ON m.channel = l.channel AND m.message_id = l.message_id
            WHERE links_fts MATCH ? AND l.dead_at IS NULL
            ORDER BY score, m.message_id DESC
            LIMIT ?
            """,
            (match, limit * 3),
        ).fetchall()

    def search_like(self, query: str, limit: int = 8, mode: str = "and") -> list:
        terms = [t for t in query.split() if len(t) >= 2]
        if not terms:
            return []
        where = " OR ".join("LOWER(m.title) LIKE ?" for _ in terms) if mode == "or" \
            else " AND ".join("LOWER(m.title) LIKE ?" for _ in terms)
        params = [f"%{t.lower()}%" for t in terms]
        return self.conn.execute(
            f"""
            SELECT l.id, m.title, m.posted_at, l.channel, l.message_id,
                   COALESCE(l.resolved_url, l.url) AS link, l.product_id, 0.0 AS score
            FROM links l
            JOIN messages m ON m.channel = l.channel AND m.message_id = l.message_id
            WHERE {where} AND l.dead_at IS NULL
            ORDER BY m.message_id DESC
            LIMIT ?
            """,
            (*params, limit * 3),
        ).fetchall()

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM messages) AS msgs,"
            " (SELECT COUNT(*) FROM links) AS links,"
            " (SELECT COUNT(*) FROM links WHERE resolved_at IS NOT NULL) AS resolved,"
            " (SELECT COUNT(DISTINCT channel) FROM messages) AS channels"
        ).fetchone()
        return dict(row)

    def close(self) -> None:
        self.conn.close()
