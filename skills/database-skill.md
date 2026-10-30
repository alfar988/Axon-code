---
name: database-skill
description: SQLite and SQL in practice: schema design, migrations with user_version, transactions, indexes and EXPLAIN, keyset pagination, upserts, backups. Python and Node examples; runnable.
---
# Database skill

SQLite covers most apps up to many gigabytes and is a single file. Reach for Postgres when you need many concurrent writers or network access.

## Open it correctly
```python
# check: runs
import sqlite3

def connect(path=":memory:"):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row                 # rows behave like dicts
    db.execute("pragma foreign_keys = on")       # off by default in SQLite
    db.execute("pragma journal_mode = wal")      # readers do not block the writer (ignored for :memory:)
    db.execute("pragma busy_timeout = 5000")     # wait instead of failing with "database is locked"
    return db

db = connect()
print(db.execute("pragma foreign_keys").fetchone()[0])
```

## Schema and migrations
Keep the schema version in the database itself and apply numbered steps in order, each in a transaction:
```python
# check: runs
import sqlite3

MIGRATIONS = [
    "create table notes (id integer primary key, title text not null, created integer not null default (strftime('%s','now')))",
    "alter table notes add column body text not null default ''",
    "create index idx_notes_created on notes(created)",
]

def migrate(db):
    version = db.execute("pragma user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        with db:                                   # commit on success, roll back on error
            db.execute(sql)
            db.execute("pragma user_version = %d" % i)
    return len(MIGRATIONS)

db = sqlite3.connect(":memory:")
assert migrate(db) == 3
assert migrate(db) == 3                             # running again changes nothing
print(db.execute("pragma user_version").fetchone()[0])
```
Never edit a migration that has shipped; add a new one. Design: one table per kind of thing, integer primary keys, `not null` and `check` constraints, foreign keys with `on delete cascade` where children make no sense alone, dates as ISO text or integer epoch (pick one).

## Queries
Always parameters (`?`), see security-skill. Fetch only the columns and rows you need. Wrap related writes in one transaction:
```python
# check: runs
import sqlite3
db = sqlite3.connect(":memory:")
db.execute("create table acct (id integer primary key, bal integer not null check (bal >= 0))")
db.executemany("insert into acct values (?, ?)", [(1, 100), (2, 0)])

def transfer(db, src, dst, amount):
    with db:                                        # both updates or neither
        db.execute("update acct set bal = bal - ? where id = ?", (amount, src))
        db.execute("update acct set bal = bal + ? where id = ?", (amount, dst))

transfer(db, 1, 2, 60)
try:
    transfer(db, 1, 2, 60)                          # would go negative: the check constraint rejects it
except sqlite3.IntegrityError:
    pass
assert [r[0] for r in db.execute("select bal from acct order by id")] == [40, 60]
```

## Indexes: look at the plan
```python
# check: runs
import sqlite3
db = sqlite3.connect(":memory:")
db.execute("create table log (id integer primary key, user_id integer, at integer)")
db.executemany("insert into log (user_id, at) values (?, ?)", [(i % 50, i) for i in range(5000)])
q = "select * from log where user_id = ? order by at desc limit 20"
before = " ".join(r[3] for r in db.execute("explain query plan " + q, (7,)))
db.execute("create index idx_log_user_at on log(user_id, at)")
after = " ".join(r[3] for r in db.execute("explain query plan " + q, (7,)))
assert "SCAN" in before and "idx_log_user_at" in after
print(after)
```
Index the columns you filter and sort by, in that order. Each index slows writes; do not index everything.

## Pagination that stays fast
`offset 100000` reads and throws away 100000 rows. Use keyset pagination: remember the last id.
```python
# check: runs
import sqlite3
db = sqlite3.connect(":memory:")
db.execute("create table items (id integer primary key, name text)")
db.executemany("insert into items (name) values (?)", [("n%d" % i,) for i in range(25)])

def page(db, after_id=0, size=10):
    rows = db.execute("select id, name from items where id > ? order by id limit ?", (after_id, size)).fetchall()
    return rows, (rows[-1][0] if len(rows) == size else None)

seen, cursor = [], 0
while cursor is not None:
    rows, cursor = page(db, cursor)
    seen += [r[0] for r in rows]
assert seen == list(range(1, 26))
```

## Upsert, counters, JSON
```sql
insert into stats (key, hits) values (?, 1)
on conflict(key) do update set hits = hits + 1;
select json_extract(data, '$.user.name') from events where json_extract(data, '$.type') = 'login';
```
## N+1 queries
Loading a list, then one query per row, is the usual cause of a slow page. Use a join, or one `where id in (...)` query for all children.

## Backup and safety
`sqlite3 app.db ".backup backup.db"` or `db.backup(other_connection)` while the app runs; never copy the file of a live WAL database by hand. Keep the database file out of git. Before a destructive change, back up first.

## Node
`node:sqlite` ships with recent Node versions (experimental); `better-sqlite3` is the common package (`npm install better-sqlite3`): `db.prepare("select * from t where id = ?").get(id)`. Same rules: parameters, transactions (`db.transaction(fn)`), indexes.
