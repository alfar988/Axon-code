---
name: database-skill
description: SQLite and SQL in practice: schema design, migrations with user_version, transactions, indexes and EXPLAIN, keyset pagination, upserts, backups. Python and Node examples; runnable.
---
# Database skill

SQLite covers most apps up to many gigabytes and is a single file. Reach for Postgres when you need many concurrent writers or network access.

## Quick rules (read first)
1. Every query uses parameters. User text is data, never part of the SQL string.
2. Several writes that belong together go in one transaction.
3. SQLite: turn on `PRAGMA foreign_keys = ON` for every connection, and use `with db:` so changes commit or roll back.
4. Add an index for columns used in `WHERE`, `JOIN` and `ORDER BY` of frequent queries. Check with `EXPLAIN QUERY PLAN`.
5. Change the schema with an ordered migration, and back up the file first.
6. Select only the columns you need and always limit lists.

## Safety in this skill
- Do not write queries or exports whose purpose is to copy other people's personal data, or to get around access control (reading rows the signed-in user does not own).
- Never store passwords in plain text; store a salted hash. Keep only the personal data the feature needs, and say where the file lives.

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

## Good and bad examples

### 1. Parameters
Bad: the quote in the name changes the meaning of the query.
```python
db.execute("SELECT id FROM users WHERE name = '" + name + "'")
```
Good: the text stays data.
```python
# check: runs
import sqlite3

db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
db.execute("INSERT INTO users (name) VALUES (?)", ("ann",))
evil = "x' OR '1'='1"
assert db.execute("SELECT id FROM users WHERE name = ?", (evil,)).fetchall() == []
assert db.execute("SELECT id FROM users WHERE name = ?", ("ann",)).fetchone() == (1,)
```

### 2. Transactions
Bad: two updates that must happen together, with a crash possible between them.
Good: one transaction that rolls back as a whole.
```python
# check: runs
import sqlite3

db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE acct (id INTEGER PRIMARY KEY, bal INTEGER CHECK (bal >= 0))")
db.executemany("INSERT INTO acct (id, bal) VALUES (?, ?)", [(1, 100), (2, 0)])
db.commit()
try:
    with db:                                    # commit on success, rollback on error
        db.execute("UPDATE acct SET bal = bal + 150 WHERE id = 2")
        db.execute("UPDATE acct SET bal = bal - 150 WHERE id = 1")   # breaks the CHECK
except sqlite3.IntegrityError:
    pass
assert [r[0] for r in db.execute("SELECT bal FROM acct ORDER BY id")] == [100, 0]
```

### 3. Counters
Bad: read the value, add one in Python, write it back. Two requests at once lose a count.
Good: let the database do it in one statement.
```python
# check: runs
import sqlite3

db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE hits (page TEXT PRIMARY KEY, n INTEGER NOT NULL)")
for _ in range(3):
    db.execute("INSERT INTO hits (page, n) VALUES (?, 1) ON CONFLICT(page) DO UPDATE SET n = n + 1", ("/home",))
assert db.execute("SELECT n FROM hits WHERE page = '/home'").fetchone()[0] == 3
```

### 4. N+1 queries
Bad: one query for the orders, then one more query per order for its customer.
Good: one `JOIN`, or one `WHERE id IN (...)` for all the ids.

### 5. Long lists
Bad: `OFFSET 100000` gets slower as the page number grows.
Good: keyset pages: `WHERE id > ? ORDER BY id LIMIT 50`, passing the last id you saw.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| `database is locked` | Keep transactions short; one writer at a time; `PRAGMA busy_timeout = 5000` |
| Foreign keys not enforced | `PRAGMA foreign_keys = ON` on every new connection |
| Slow `LIKE '%word%'` | Use FTS5, or accept the cost for small tables |
| Dates stored as free text | Store ISO 8601 (`2026-11-07T10:00:00Z`) so they sort correctly |
| Schema change on live data without backup | Copy the file first; make the migration repeatable |
| `SELECT *` in application code | Name the columns |

## Checklist before you finish
- [ ] No query is built by joining strings.
- [ ] Related writes share one transaction.
- [ ] Foreign keys, unique constraints and NOT NULL express the rules in the schema.
- [ ] Frequent filters have an index, confirmed with `EXPLAIN QUERY PLAN`.
- [ ] Lists are limited and paginated; a backup exists before a migration.
