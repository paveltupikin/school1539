"""Versioned exercise content shared by SQLite and the static practice site."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
BANK_DIR = ROOT / "bank"
EXPORT = ROOT / "docs" / "assets" / "math-bank.js"
OVERRIDES = {"topic", "prompt", "answer", "solution", "kind", "options", "public_id"}
PUBLIC_FIELDS = {"topic", "prompt", "number", "kind", "context", "options", "image", "alt", "figures", "items", "public_id", "card_id"}
KINDS = {"number", "sequence", "choice", "written"}


def load_seed():
    return json.loads((BANK_DIR / "oge-math.json").read_text(encoding="utf-8"))


def install(db, seed):
    """Replace the seeded catalog atomically. Attempts contain their own snapshots."""
    db.executescript((BANK_DIR / "catalog.sql").read_text(encoding="utf-8"))
    exam, subject = seed["exam"], seed["subject"]
    public_ids = [task["public_id"] for task in seed["tasks"]]
    public_ids.extend(card["public_id"] for card in seed["cards"] if "public_id" in card)
    if len(set(public_ids)) != len(public_ids):
        raise ValueError("Duplicate public exercise ID")
    with db:
        course = (exam, subject)
        db.execute("DELETE FROM bank_card WHERE exam = ? AND subject = ?", course)
        db.execute("DELETE FROM bank_test_task WHERE test_id IN (SELECT id FROM bank_test WHERE exam = ? AND subject = ?)", course)
        db.execute("DELETE FROM bank_test WHERE exam = ? AND subject = ?", course)
        db.execute("DELETE FROM bank_task WHERE exam = ? AND subject = ?", course)
        db.executemany("""INSERT INTO bank_source VALUES (?, ?)
                          ON CONFLICT(id) DO UPDATE SET title=excluded.title""", seed["sources"].items())
        db.executemany("""INSERT INTO bank_context VALUES (?, ?, ?)
                          ON CONFLICT(id) DO UPDATE SET source_id=excluded.source_id, content=excluded.content""",
                       ((c["id"], c["source"], json.dumps(c)) for c in seed["contexts"]))
        for task in seed["tasks"]:
            if task["kind"] not in KINDS:
                raise ValueError(f"Unknown answer type for {task['id']}")
            db.execute("INSERT INTO bank_task VALUES (?, ?, ?, ?, ?, ?)",
                       (task["id"], task["source"], task.get("context"), exam, subject, json.dumps(task)))
        for test in seed["tests"]:
            db.execute("INSERT INTO bank_test VALUES (?, ?, ?, ?)", (test["id"], exam, subject, test["title"]))
            db.executemany("INSERT INTO bank_test_task VALUES (?, ?, ?)",
                           ((test["id"], pos, task) for pos, task in enumerate(test["tasks"], 1)))
        for pos, card in enumerate(seed["cards"], 1):
            overrides = {key: value for key, value in card.items() if key in OVERRIDES}
            db.execute("INSERT INTO bank_card VALUES (?, ?, ?, ?, ?, ?)",
                       (card["id"], card["task"], exam, subject, pos, json.dumps(overrides)))


def questions(db, exam, subject, mode):
    if mode == "quiz":
        query = """SELECT c.*, s.title AS source_label, ctx.content AS shared
                   FROM database_cards c JOIN bank_source s ON s.id = c.source_id
                   LEFT JOIN bank_context ctx ON ctx.id = c.context_id
                   WHERE c.exam = ? AND c.subject = ? ORDER BY c.position"""
    elif mode == "feed":
        query = """SELECT t.*, s.title AS source_label, ctx.content AS shared
                   FROM bank_task t JOIN bank_source s ON s.id = t.source_id
                   LEFT JOIN bank_context ctx ON ctx.id = t.context_id
                   WHERE t.exam = ? AND t.subject = ? ORDER BY t.id"""
    else:
        query = """SELECT t.*, s.title AS source_label, ctx.content AS shared
                   FROM database_tests t JOIN bank_source s ON s.id = t.source_id
                   LEFT JOIN bank_context ctx ON ctx.id = t.context_id
                   WHERE t.exam = ? AND t.subject = ? AND t.test_id = (
                     SELECT id FROM bank_test WHERE exam = t.exam AND subject = t.subject ORDER BY id LIMIT 1
                   ) ORDER BY t.position"""
    result = []
    for entry in db.execute(query, (exam, subject)):
        task = json.loads(entry["content"])
        if mode == "quiz":
            task.update(json.loads(entry["overrides"]))
            task["card_id"] = entry["card_id"]
        elif mode == "test":
            task["number"] = entry["position"]
        task["context"] = json.loads(entry["shared"]) if entry["shared"] else None
        task["source_label"] = entry["source_label"]
        result.append(task)
    return result


def public_question(task):
    data = {key: value for key, value in task.items() if key in PUBLIC_FIELDS}
    if data.get("context"):
        data["context"] = {key: value for key, value in data["context"].items() if key != "source"}
    return data


def task_feed(db, exam, subject):
    tasks = questions(db, exam, subject, "feed")
    seen = {task["public_id"] for task in tasks}
    steps = [card for card in questions(db, exam, subject, "quiz") if card["public_id"] not in seen]
    return sorted((public_question(task) for task in tasks + steps), key=lambda task: task["public_id"])


def snapshot_questions(db, saved):
    """Add IDs to attempts created before the public catalog was introduced."""
    missing_ids = any(task.get("id") and not task.get("public_id") for task in saved)
    if not missing_ids:
        return saved
    tasks = {task["id"]: task for task in questions(db, "oge", "math", "feed")}
    cards = {card["card_id"]: card for card in questions(db, "oge", "math", "quiz")}
    for task in saved:
        match = cards.get(task.get("card_id")) or tasks.get(task.get("id"))
        if match and not task.get("public_id"):
            task["public_id"] = match["public_id"]
            task["source_label"] = match["source_label"]
    return saved


def export_text():
    seed = load_seed()
    exam, subject = seed["exam"], seed["subject"]
    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        install(db, seed)
        data = {
            "cards": questions(db, exam, subject, "quiz"),
            "test": questions(db, exam, subject, "test"),
            "feed": task_feed(db, exam, subject),
        }
    return "// Generated by python3 question_bank.py.\nwindow.ogeMathBank = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"


if __name__ == "__main__":
    output = export_text()
    if sys.argv[1:] == ["--check"]:
        if not EXPORT.exists() or EXPORT.read_text(encoding="utf-8") != output:
            sys.exit("Run python3 question_bank.py to update the GitHub Pages bank.")
    else:
        EXPORT.write_text(output, encoding="utf-8")
