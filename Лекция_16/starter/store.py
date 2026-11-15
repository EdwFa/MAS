"""Состояние случая вне процесса: SQLite (лекция 16, слайды 16, 20, 24).

cases   — запись случая: шаг графа, taskId, contextId, статус, сделанные записи, версия схемы.
pushes  — уже принятые уведомления (дубли — норма).
ledger  — журнал записей в карту: ключ → ссылка.
events  — трасса случая; переживает перезапуск, как и всё остальное.
Окно модели не хранится: его собирают заново из записи случая.
"""
import contextlib
import json
import sqlite3
import time

SCHEMA = "v3"


class CaseStore:
    def __init__(self, path):
        self.path = str(path)
        with self._db() as db:
            db.executescript("""
            create table if not exists cases (case_id text primary key, data text, schema text, updated real);
            create table if not exists pushes (task_id text, stamp text, primary key (task_id, stamp));
            create table if not exists ledger (key text primary key, ref text);
            create table if not exists events (n integer primary key autoincrement, case_id text,
                                               kind text, data text, t real);""")

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, isolation_level=None)     # каждая запись сразу на диске
        try:
            yield db
        finally:
            db.close()

    # --- случай ------------------------------------------------------------
    def save(self, rec):
        rec = {**rec, "schema": SCHEMA}
        with self._db() as db:
            db.execute("insert into cases values (?, ?, ?, ?) on conflict(case_id) do update set "
                       "data = excluded.data, schema = excluded.schema, updated = excluded.updated",
                       (rec["case"], json.dumps(rec, ensure_ascii=False), SCHEMA, time.time()))
        return rec

    def load(self, case_id):
        with self._db() as db:
            row = db.execute("select data, schema from cases where case_id = ?", (case_id,)).fetchone()
        if row is None:
            return None
        rec = json.loads(row[0])
        return migrate(rec, row[1])

    def case_by_task(self, task_id):
        with self._db() as db:
            for (data,) in db.execute("select data from cases"):
                rec = json.loads(data)
                if rec.get("lab", {}).get("taskId") == task_id:
                    return rec
        return None

    # --- уведомления -------------------------------------------------------
    def seen_push(self, task_id, stamp):
        """True, если такое уведомление уже было; иначе запоминает его."""
        with self._db() as db:
            try:
                db.execute("insert into pushes values (?, ?)", (task_id, str(stamp)))
                return False
            except sqlite3.IntegrityError:
                return True

    # --- журнал записей ----------------------------------------------------
    def get(self, key):
        with self._db() as db:
            row = db.execute("select ref from ledger where key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key, ref):
        with self._db() as db:
            db.execute("insert or ignore into ledger values (?, ?)", (key, ref))

    # --- трасса ------------------------------------------------------------
    def event(self, case_id, kind, **data):
        with self._db() as db:
            db.execute("insert into events (case_id, kind, data, t) values (?, ?, ?, ?)",
                       (case_id, kind, json.dumps(data, ensure_ascii=False, default=str), time.time()))

    def events(self, case_id):
        with self._db() as db:
            return [{"kind": k, **json.loads(d)} for k, d in
                    db.execute("select kind, data from events where case_id = ? order by n", (case_id,))]


def migrate(rec, schema):
    """Деплой посреди задачи (слайд 24): новый код читает старые записи."""
    if schema == "v2":                       # пример: в v2 статус лаборатории лежал отдельным полем
        rec.setdefault("lab", {})["status"] = rec.pop("lab_status", None)
        rec["schema"] = "v3"
    return rec
