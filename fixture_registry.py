"""Local fixture observations; never treat stale cache as live confirmation."""
import json
import logging
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

def _path():
    return Path(os.getenv('TITAN_DB','./data/titan.sqlite3'))

def store(record, names):
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=5) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS fixture_observations
                (source TEXT NOT NULL, checked TEXT NOT NULL, teams TEXT NOT NULL,
                kickoff TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(source, checked))""")
            db.execute("INSERT OR IGNORE INTO fixture_observations VALUES (?,?,?,?,?)",
                       (record['source'],record['checked'],json.dumps(sorted(names)),
                        record['kickoff'],json.dumps(record,ensure_ascii=False)))
    except (OSError,sqlite3.Error,KeyError,TypeError,ValueError) as exc:
        logging.warning('T1 registry store: %s',type(exc).__name__)

def recent(names, kickoff, max_age_minutes=10):
    """Return observations for inspection only; callers must revalidate before prediction."""
    try:
        if not _path().exists():
            return []
        limit = (datetime.now(timezone.utc)-timedelta(minutes=max_age_minutes)).isoformat()
        with sqlite3.connect(_path(),timeout=5) as db:
            rows = db.execute("""SELECT body FROM fixture_observations
                WHERE teams=? AND kickoff=? AND checked>=? ORDER BY checked DESC LIMIT 30""",
                (json.dumps(sorted(names)),kickoff,limit)).fetchall()
        return [json.loads(row[0]) for row in rows]
    except (OSError,sqlite3.Error,ValueError) as exc:
        logging.warning('T1 registry read: %s',type(exc).__name__)
        return []
