"""Демонстрационный портал. Запуск: python server.py."""

import argparse
from contextlib import closing
from decimal import Decimal
from getpass import getpass
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from content import BANK, EXAMS, SUBJECTS
import question_bank
from workbook import xlsx

ROOT = Path(__file__).resolve().parent
DB = os.environ.get("PORTAL_DB", str(ROOT / "portal.sqlite3"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS user(id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL, grade TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session(token TEXT PRIMARY KEY, uid INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS grp(id INTEGER PRIMARY KEY, teacher INTEGER NOT NULL, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS member(gid INTEGER NOT NULL, uid INTEGER NOT NULL, PRIMARY KEY(gid,uid));
CREATE TABLE IF NOT EXISTS assignment(id INTEGER PRIMARY KEY, gid INTEGER NOT NULL, uid INTEGER,
  title TEXT NOT NULL, exam TEXT NOT NULL, subject TEXT NOT NULL, mode TEXT NOT NULL,
  target INTEGER NOT NULL, minutes INTEGER NOT NULL, questions TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempt(id TEXT PRIMARY KEY, uid INTEGER NOT NULL, aid INTEGER,
  exam TEXT NOT NULL, subject TEXT NOT NULL, mode TEXT NOT NULL, questions TEXT NOT NULL,
  deadline INTEGER, result TEXT, correct INTEGER, total INTEGER);
CREATE INDEX IF NOT EXISTS attempt_user ON attempt(uid,aid);
"""
REPORT = ["Ученик", "Класс", "Работа", "Экзамен", "Предмет", "Цель", "Выполнено", "Верно", "Оценка (демо)"]


class Error(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(db):
    db.executescript(SCHEMA)
    if "scope" not in {column[1] for column in db.execute("PRAGMA table_info(attempt)")}:
        db.execute("ALTER TABLE attempt ADD COLUMN scope TEXT NOT NULL DEFAULT ''")
    question_bank.install_all(db)


def row(db, query, *args):
    return db.execute(query, args).fetchone()


def rows(db, query, *args):
    return [dict(r) for r in db.execute(query, args)]


def string(data, key, low=1, high=120):
    value = data.get(key)
    if not isinstance(value, str) or not low <= len(value.strip()) <= high:
        raise Error("Проверьте заполнение полей.")
    return value.strip()


def number(data, key, low, high):
    value = data.get(key)
    if type(value) is not int or not low <= value <= high:
        raise Error(f"Введите число от {low} до {high}.")
    return value


def digest(value, salt):
    return hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()


def user_create(db, data, role):
    login = string(data, "login", 3, 40).lower()
    if not re.fullmatch(r"[a-z0-9_.-]+", login):
        raise Error("В логине допустимы латинские буквы, цифры, точка, дефис и подчёркивание.")
    name = string(data, "name", 2, 80)
    password = string(data, "password", 10, 128)
    grade = string(data, "grade", 1, 2) if role == "student" else ""
    if role == "student" and grade not in {"9", "10", "11"}:
        raise Error("Выберите 9, 10 или 11 класс.")
    salt = secrets.token_hex(16)
    try:
        return db.execute("INSERT INTO user(login,name,grade,password,role) VALUES(?,?,?,?,?)",
                          (login, name, grade, salt + ":" + digest(password, salt), role)).lastrowid
    except sqlite3.IntegrityError:
        raise Error("Этот логин уже занят.", 409) from None


def public_user(db, uid):
    found = row(db, "SELECT id,name,grade,role FROM user WHERE id=?", uid)
    return dict(found) if found else None


def course(data):
    exam, subject, mode = (string(data, key) for key in ("exam", "subject", "mode"))
    if (exam, subject) not in BANK or mode not in {"quiz", "test"}:
        raise Error("Раздел не найден.", 404)
    return exam, subject, mode


def normalize(value):
    return " ".join(value.casefold().replace("ё", "е").replace(",", ".").split())


def matches(task, answer):
    expected = task["answer"]
    if task["kind"] == "number":
        value = answer.strip().replace("−", "-").replace(",", ".")
        value = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d)", "", value)
        return bool(re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)", value)) and (
            Decimal(value) == Decimal(expected.replace("−", "-").replace(",", "."))
        )
    if task["kind"] == "set":
        digits = re.sub(r"[\s,;]", "", answer)
        return bool(re.fullmatch(r"[1-9]+", digits)) and len(set(digits)) == len(digits) and set(digits) == set(expected)
    if task["kind"] in {"sequence", "choice"}:
        return re.sub(r"\s", "", answer) == expected
    def key(value):
        result = normalize(value)
        return re.sub(r"\s", "", result) if task.get("compact_answer") else result
    return any(key(answer) == key(value) for value in task.get("answers") or [expected])


def wrong_cards(db, uid, exam, subject):
    latest = {}
    for attempt in db.execute("SELECT questions,result FROM attempt WHERE uid=? AND exam=? AND subject=? AND mode='quiz' AND result IS NOT NULL ORDER BY rowid DESC LIMIT 500", (uid, exam, subject)):
        result = json.loads(attempt["result"])
        if result.get("skipped"): continue
        for task, detail in zip(json.loads(attempt["questions"]), result.get("details", [])):
            if task.get("public_id"): latest.setdefault(task["public_id"], detail[2])
    return {key for key, good in latest.items() if good is False}


def as_task(question):
    if isinstance(question, dict):
        return question
    topic, prompt, answer = question
    return {"topic": topic, "prompt": prompt, "answer": answer, "kind": "text"}


def assignments(db, uid):
    return rows(db, """
      SELECT a.id,a.title,a.exam,a.subject,a.mode,a.target,a.minutes,g.name AS group_name,
        COALESCE(SUM(t.total),0) AS done,COALESCE(SUM(t.correct),0) AS correct
      FROM assignment a JOIN grp g ON g.id=a.gid JOIN member m ON m.gid=g.id AND m.uid=?
      LEFT JOIN attempt t ON t.aid=a.id AND t.uid=m.uid
      WHERE a.uid IS NULL OR a.uid=m.uid GROUP BY a.id ORDER BY a.id DESC
    """, uid)


def saved_questions(db, serialized):
    return question_bank.snapshot_questions(db, [as_task(question) for question in json.loads(serialized)])


def result_payload(result, questions, mode):
    payload = dict(result, questions=[question_bank.public_question(q) for q in questions])
    if mode == "test":
        sources = {question["source_label"] for question in questions if question.get("source_label")}
        payload["source"] = " · ".join(sorted(sources))
    return payload


def attempt_start(db, data, uid):
    exam, subject, mode = course(data)
    aid = data.get("assignment")
    db.execute("BEGIN IMMEDIATE")
    bank = question_bank.questions(db, exam, subject, mode) or BANK[exam, subject]
    scope = ""
    if exam == "oge" and subject == "russ" and aid is None:
        selected = {key: data[key] for key in ("test", "topic", "id", "review") if data.get(key)}
        if any(not isinstance(value, str) for key, value in selected.items() if key != "review"):
            raise Error("Проверьте выбор тренировки.")
        if mode == "test" and selected.get("test"):
            bank = question_bank.questions(db, exam, subject, mode, selected["test"])
        if mode == "quiz":
            if selected.get("topic"): bank = [q for q in bank if q["topic"] == selected["topic"]]
            if selected.get("id"): bank = [q for q in bank if q["public_id"] == selected["id"]]
            if selected.get("review"):
                wrong = wrong_cards(db, uid, exam, subject)
                bank = [q for q in bank if q["public_id"] in wrong]
        if not bank: raise Error("В этой подборке пока нет карточек или работ. Выберите другую тему.")
        scope = json.dumps(selected, sort_keys=True) if selected else ""
    deadline = None
    if aid is not None:
        aid = number(data, "assignment", 1, 2**31 - 1)
        assignment = next((a for a in assignments(db, uid) if a["id"] == aid), None)
        if not assignment or (exam, subject, mode) != tuple(assignment[k] for k in ("exam", "subject", "mode")):
            raise Error("Задание не найдено.", 404)
        if mode == "quiz" and assignment["done"] >= assignment["target"]:
            raise Error("Норма выполнена. Продолжите в свободном тренажёре.", 409)
        bank = json.loads(row(db, "SELECT questions FROM assignment WHERE id=?", aid)[0]) or bank
        if assignment["minutes"]:
            deadline = int(time.time()) + assignment["minutes"] * 60
    saved = row(db, """
      SELECT * FROM attempt WHERE uid=? AND exam=? AND subject=? AND mode=? AND aid IS ?
      AND scope=? AND (result IS NULL OR (mode='test' AND aid IS NOT NULL)) ORDER BY rowid DESC LIMIT 1
    """, uid, exam, subject, mode, aid, scope)
    if saved:
        questions = saved_questions(db, saved["questions"])
        if saved["result"]:
            return {"result": result_payload(json.loads(saved["result"]), questions, mode)}
        attempt_id, deadline = saved["id"], saved["deadline"]
    else:
        questions = bank
        if mode == "quiz":
            count = row(db, "SELECT COUNT(*) FROM attempt WHERE uid=? AND exam=? AND subject=? AND mode='quiz' AND aid IS ? AND scope=?",
                        uid, exam, subject, aid, scope)[0]
            questions = [bank[count % len(bank)]]
        questions = [as_task(question) for question in questions]
        attempt_id = secrets.token_urlsafe(18)
        db.execute("INSERT INTO attempt(id,uid,aid,exam,subject,mode,questions,deadline,scope) VALUES(?,?,?,?,?,?,?,?,?)",
                   (attempt_id, uid, aid, exam, subject, mode, json.dumps(questions), deadline, scope))
    return {"id": attempt_id, "deadline": deadline,
            "questions": [question_bank.public_question(question) for question in questions]}


def attempt_finish(db, data, uid):
    db.execute("BEGIN IMMEDIATE")
    attempt = row(db, "SELECT * FROM attempt WHERE id=? AND uid=?", string(data, "id"), uid)
    if not attempt:
        raise Error("Попытка не найдена.", 404)
    questions = saved_questions(db, attempt["questions"])
    if attempt["result"]:
        result = json.loads(attempt["result"])
        if result.get("skipped"):
            raise Error("Карточка уже пропущена.", 409)
        return result_payload(result, questions, attempt["mode"])
    answers = data.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions) or any(
        not isinstance(answer, str) or len(answer) > (4000 if question["kind"] == "written" else 240)
        for question, answer in zip(questions, answers)
    ):
        raise Error("Проверьте ответы.")
    expired = attempt["deadline"] is not None and int(time.time()) >= attempt["deadline"]
    details = []
    for question, answer in zip(questions, answers):
        written = question["kind"] == "written"
        correct = None if written else not expired and matches(question, answer)
        details.append([question["prompt"], question["answer"], correct,
                        question.get("solution"), answer])
    graded = [detail for detail in details if detail[2] is not None]
    result = {"expired": expired, "details": details,
              "correct": sum(detail[2] for detail in graded), "total": len(graded)}
    db.execute("UPDATE attempt SET result=?,correct=?,total=? WHERE id=?",
               (json.dumps(result), result["correct"], result["total"], attempt["id"]))
    return result_payload(result, questions, attempt["mode"])


def attempt_skip(db, data, uid):
    db.execute("BEGIN IMMEDIATE")
    attempt = row(db, "SELECT * FROM attempt WHERE id=? AND uid=?", string(data, "id"), uid)
    if not attempt or attempt["mode"] != "quiz" or attempt["aid"] is not None:
        raise Error("Эту карточку нельзя пропустить.", 404)
    if attempt["result"]:
        if json.loads(attempt["result"]).get("skipped"):
            return {}
        raise Error("На карточку уже ответили.", 409)
    db.execute("UPDATE attempt SET result=? WHERE id=?", (json.dumps({"skipped": True}), attempt["id"]))
    return {}


def student_api(db, method, path, data, uid):
    if (method, path) == ("GET", "/progress"):
        progress = rows(db, """
          SELECT exam,subject,SUM(total) AS answered,SUM(correct) AS correct,
            COUNT(CASE WHEN mode='test' THEN 1 END) AS tests
          FROM attempt WHERE uid=? AND total IS NOT NULL GROUP BY exam,subject
        """, uid)
        return {"progress": progress, "assignments": assignments(db, uid)}
    if (method, path) == ("POST", "/join"):
        group = row(db, "SELECT id,name FROM grp WHERE code=?", string(data, "code", 8, 8).upper())
        if not group:
            raise Error("Группа не найдена.", 404)
        db.execute("INSERT OR IGNORE INTO member VALUES(?,?)", (group["id"], uid))
        return {"name": group["name"]}
    if (method, path) == ("POST", "/start"):
        return attempt_start(db, data, uid)
    if (method, path) == ("POST", "/skip"):
        return attempt_skip(db, data, uid)
    if (method, path) == ("POST", "/finish"):
        return attempt_finish(db, data, uid)
    raise Error("Действие недоступно для ученика.", 403)


def report(db, gid):
    results = rows(db, """
      SELECT u.name,u.grade,a.title,a.exam,a.subject,a.mode,a.target,
        COALESCE(SUM(t.total),0) AS answered,COALESCE(SUM(t.correct),0) AS correct
      FROM assignment a JOIN member m ON m.gid=a.gid JOIN user u ON u.id=m.uid
      LEFT JOIN attempt t ON t.aid=a.id AND t.uid=u.id
      WHERE a.gid=? AND (a.uid IS NULL OR a.uid=u.id)
      GROUP BY a.id,u.id ORDER BY a.id DESC,u.name
    """, gid)
    output = []
    for r in results:
        percent = 100 * r["correct"] // r["target"]
        grade = (5 if percent >= 85 else 4 if percent >= 70 else 3 if percent >= 50 else 2)
        output.append([r["name"], r["grade"], r["title"], EXAMS[r["exam"]], SUBJECTS[r["subject"]],
                       r["target"], r["answered"], r["correct"], grade if r["mode"] == "test" and r["answered"] else ""])
    return output


def teacher_api(db, method, path, data, uid):
    if (method, path) == ("GET", "/groups"):
        return {"groups": rows(db, "SELECT id,name,code FROM grp WHERE teacher=? ORDER BY id DESC", uid)}, {}
    if (method, path) == ("POST", "/groups"):
        gid = db.execute("INSERT INTO grp(teacher,name,code) VALUES(?,?,?)",
                         (uid, string(data, "name", 2, 80), secrets.token_hex(4).upper())).lastrowid
        return {"id": gid}, {}
    route = re.fullmatch(r"/groups/([0-9]{1,10})(/export|/assign)?", path)
    if not route:
        raise Error("Действие недоступно для учителя.", 403)
    gid = int(route[1])
    if not row(db, "SELECT id FROM grp WHERE id=? AND teacher=?", gid, uid):
        raise Error("Группа не найдена.", 404)
    if (method, route[2]) == ("GET", "/export"):
        return xlsx([REPORT, *report(db, gid)]), {"Content-Disposition": f'attachment; filename="group-{gid}.xlsx"'}
    members = rows(db, "SELECT u.id,u.name,u.grade FROM member m JOIN user u ON u.id=m.uid WHERE m.gid=? ORDER BY u.name", gid)
    if (method, route[2]) == ("GET", None):
        works = rows(db, """
          SELECT a.title,a.exam,a.subject,a.mode,a.target,a.minutes,u.name AS student FROM assignment a
          LEFT JOIN user u ON u.id=a.uid WHERE a.gid=? ORDER BY a.id DESC
        """, gid)
        return {"members": members, "works": works, "headers": REPORT, "results": report(db, gid)}, {}
    if (method, route[2]) == ("POST", "/assign"):
        exam, subject, mode = course(data)
        student = data.get("student")
        if student is not None:
            student = number(data, "student", 1, 2**31 - 1)
            if mode != "test" or student not in {m["id"] for m in members}:
                raise Error("Персональный пробник можно назначить ученику этой группы.")
        minutes, questions = 0, []
        if mode == "quiz":
            target = number(data, "target", 1, 300)
        else:
            minutes = number(data, "minutes", 0, 300)
            items = data.get("questions", [])
            if not isinstance(items, list) or len(items) > 30 or any(not isinstance(i, dict) for i in items):
                raise Error("Добавьте до 30 вопросов.")
            questions = [["Вопрос учителя", string(i, "text", 2, 600), string(i, "answer", 1, 240)] for i in items]
            target = len(questions) if questions else sum(
                as_task(question)["kind"] != "written"
                for question in (question_bank.questions(db, exam, subject, "test") or BANK[exam, subject])
            )
        db.execute("INSERT INTO assignment(gid,uid,title,exam,subject,mode,target,minutes,questions) VALUES(?,?,?,?,?,?,?,?,?)",
                   (gid, student, string(data, "title", 2), exam, subject, mode, target, minutes, json.dumps(questions)))
        return {}, {}
    raise Error("Действие не найдено.", 404)


def cookie(token, age):
    secure = "; Secure" if os.environ.get("PORTAL_SECURE_COOKIE") == "1" else ""
    return {"Set-Cookie": f"portal={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}"}


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def api(db, method, path, data, token):
    key = token_hash(token)
    now = int(time.time())
    found = row(db, "SELECT uid FROM session WHERE token=? AND expires>?", key, now)
    user = public_user(db, found["uid"]) if found else None
    if (method, path) == ("GET", "/me"):
        return {"user": user}, {}
    catalog_route = re.fullmatch(r"/oge/(math|russ)/(tasks|catalog)", path)
    if method == "GET" and catalog_route:
        if catalog_route[2] == "catalog": return question_bank.catalog(db, "oge", catalog_route[1]), {}
        return {"tasks": question_bank.task_feed(db, "oge", catalog_route[1])}, {}
    if method == "POST" and path in {"/login", "/register"}:
        if path == "/register":
            uid = user_create(db, data, "student")
        else:
            login = string(data, "login", 3, 40).lower()
            password = string(data, "password", 1, 128)
            account = row(db, "SELECT id,password FROM user WHERE login=?", login)
            salt, expected = account["password"].split(":") if account else ("0" * 32, "0" * 128)
            if not secrets.compare_digest(digest(password, salt), expected) or not account:
                raise Error("Проверьте логин и пароль.", 401)
            uid = account["id"]
        fresh, age = secrets.token_urlsafe(32), 7 * 86400
        db.execute("DELETE FROM session WHERE token=? OR expires<=?", (key, now))
        db.execute("INSERT INTO session VALUES(?,?,?)", (token_hash(fresh), uid, now + age))
        return {"user": public_user(db, uid)}, cookie(fresh, age)
    if (method, path) == ("POST", "/logout"):
        db.execute("DELETE FROM session WHERE token=?", (key,))
        return {}, cookie("", 0)
    if not user:
        raise Error("Войдите в кабинет.", 401)
    if user["role"] == "teacher":
        return teacher_api(db, method, path, data, user["id"])
    return student_api(db, method, path, data, user["id"]), {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.handle_method("GET")

    def do_POST(self):
        self.handle_method("POST")

    def handle_method(self, method):
        path = urlsplit(self.path).path
        assets = {"/styles.css": "text/css", "/app.js": "text/javascript"}
        try:
            if method == "GET" and path in assets:
                return self.reply((ROOT / path[1:]).read_bytes(), assets[path])
            if method == "GET" and re.fullmatch(r"/assets/(question-ui\.js|question-ui\.css|y27-[a-z]+(?:-[a-z]+)?\.svg)", path):
                asset = ROOT / "docs" / path[1:]
                types = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
                if asset.is_file():
                    return self.reply(asset.read_bytes(), types[asset.suffix])
            if method == "GET" and path == "/progress":
                return self.reply(b"", "text/html", status=302, headers={"Location": "/account"})
            if method == "GET" and (path in {"/", "/account", "/teacher", "/oge/math/tasks", "/oge/russ/tasks"} or re.fullmatch(
                r"/(oge|ege)(/(math|russ|history|social)(/(quiz|test))?)?", path
            )):
                return self.reply((ROOT / "index.html").read_bytes(), "text/html")
            if not path.startswith("/api/"):
                raise Error("Страница не найдена.", 404)
            data = self.read_data() if method == "POST" else {}
            token = SimpleCookie(self.headers.get("Cookie", "")).get("portal")
            with closing(connect()) as db, db:
                result, headers = api(db, method, path[4:], data, token.value if token else "")
            if isinstance(result, bytes):
                return self.reply(result, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
            self.json(result, headers=headers)
        except Error as error:
            self.json({"error": str(error)}, status=error.status)

    def read_data(self):
        if self.headers.get_content_type() != "application/json":
            raise Error("Ожидается JSON.", 415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 128_000:
                raise ValueError
            data = json.loads(self.rfile.read(size))
        except ValueError:
            raise Error("Некорректные данные.") from None
        if not isinstance(data, dict):
            raise Error("Некорректные данные.")
        return data

    def json(self, body, **options):
        self.reply(json.dumps(body, ensure_ascii=False).encode(), "application/json", **options)

    def reply(self, body, mime, status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if "spreadsheet" not in mime else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--teacher", nargs=2, metavar=("LOGIN", "NAME"))
    args = parser.parse_args()
    with closing(connect()) as db, db:
        initialize(db)
        if args.teacher:
            login, name = args.teacher
            try:
                user_create(db, {"login": login, "name": name, "password": getpass("Пароль учителя: ")}, "teacher")
            except Error as error:
                parser.exit(1, f"{error}\n")
            print("Учитель создан.")
            return
    print(f"http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
