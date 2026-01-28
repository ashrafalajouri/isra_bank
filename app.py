import os
import csv
import io
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import bcrypt
import hashlib
from itsdangerous import URLSafeSerializer, BadSignature
from starlette.middleware.sessions import SessionMiddleware

APP_NAME = "Bank Al-Isra"
# IMPORTANT: Change this SECRET_KEY in production
SECRET_KEY = "FBaa6P9yuuMHv79yoafs58UbhOUDj6NzRhWCa5HBdPMEMHZeRlCB0OXNj4ax2r9X"
SESSION_COOKIE = "session"
DB_PATH = "app.db"
UPLOAD_DIR = Path("static/uploads")
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".jfif"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="flash")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso():
    return datetime.utcnow().isoformat()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            points INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            exam_type TEXT NOT NULL CHECK (exam_type IN ('mid','final','both')),
            question_text TEXT NOT NULL,
            choice_a TEXT NOT NULL,
            choice_b TEXT NOT NULL,
            choice_c TEXT NOT NULL,
            choice_d TEXT NOT NULL,
            correct_choice TEXT NOT NULL CHECK (correct_choice IN ('A','B','C','D')),
            image_path TEXT,
            source TEXT NOT NULL DEFAULT 'past' CHECK (source IN ('past','ai')),
            explanation TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            chosen_choice TEXT NOT NULL CHECK (chosen_choice IN ('A','B','C','D')),
            is_correct INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT NOT NULL,
            subject_name TEXT,
            subject_id INTEGER,
            exam_type TEXT,
            question_text TEXT,
            choice_a TEXT,
            choice_b TEXT,
            choice_c TEXT,
            choice_d TEXT,
            proposed_correct_choice TEXT,
            proposed_explanation TEXT,
            image_path TEXT,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question_id INTEGER NOT NULL,
            report_text TEXT NOT NULL,
            proposed_correct_choice TEXT,
            proposed_explanation TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()
    ensure_column(conn, "questions", "image_path", "TEXT")
    ensure_column(conn, "questions", "source", "TEXT")
    ensure_column(conn, "suggestions", "image_path", "TEXT")

    cur.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    admin = cur.fetchone()
    if not admin:
        # IMPORTANT: Change this default admin password after first run
        cur.execute(
            """
            INSERT INTO users (username, full_name, password_hash, role, points, created_at)
            VALUES (?, ?, ?, 'admin', 0, ?)
            """,
            ("ashraf", "Ashraf Alajouri", hash_password("tCMQq5Y9u40-lqVVLNuwQw"), now_iso()),
        )
        conn.commit()

    conn.close()


# ---------- Auth helpers ----------

def get_serializer():
    return URLSafeSerializer(SECRET_KEY, salt="session")



def ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()


def save_upload_image(file: UploadFile) -> Optional[str]:
    if not file or not file.filename:
        return None
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        # fall back to content type if extension is missing/unknown
        if file.content_type and file.content_type.startswith("image/"):
            ext = ".jpg"
        else:
            return None
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name
    with dest.open("wb") as f:
        f.write(file.file.read())
    return f"uploads/{name}"


def hash_password(password: str) -> str:
    # bcrypt limit is 72 bytes; pre-hash if longer
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = hashlib.sha256(pw_bytes).digest()
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = hashlib.sha256(pw_bytes).digest()
    return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))


def get_current_user(request: Request):
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    s = get_serializer()
    try:
        data = s.loads(cookie)
    except BadSignature:
        return None
    user_id = data.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def login_user(response: RedirectResponse, user_id: int):
    s = get_serializer()
    token = s.dumps({"user_id": user_id})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")


def logout_user(response: RedirectResponse):
    response.delete_cookie(SESSION_COOKIE)


def require_user(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return user


def require_admin(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/login", status_code=303)
    return user


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "flash": request.session.pop("flash", None),
        },
    )


@app.get("/questions", response_class=HTMLResponse)
def questions_home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(
        "questions_home.html",
        {"request": request, "user": user, "flash": request.session.pop("flash", None)},
    )


@app.get("/questions/past", response_class=HTMLResponse)
def questions_past(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(
        "questions_past.html",
        {"request": request, "user": user, "flash": request.session.pop("flash", None)},
    )


@app.get("/subjects", response_class=HTMLResponse)
def subjects_list(request: Request, source: str = "past", exam: Optional[str] = None):
    user = get_current_user(request)
    if source not in ("past", "ai"):
        source = "past"
    if source == "past":
        if exam not in ("mid", "final", "both"):
            return RedirectResponse(url="/questions/past", status_code=303)
    else:
        exam = None
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()
    conn.close()
    return templates.TemplateResponse(
        "subjects_list.html",
        {
            "request": request,
            "user": user,
            "subjects": subjects,
            "source": source,
            "exam": exam or "",
            "flash": request.session.pop("flash", None),
        },
    )


@app.get("/register", response_class=HTMLResponse)
def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "flash": request.session.pop("flash", None)})


@app.post("/register")
def register_post(request: Request, username: str = Form(...), password: str = Form(...), full_name: Optional[str] = Form(None)):
    request.session["flash"] = "التسجيل للطلاب متوقف. الدخول متاح فقط للإدارة."
    return RedirectResponse(url="/register", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "flash": request.session.pop("flash", None)})


@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    conn.close()
    if not user or not verify_password(password, user["password_hash"]):
        request.session["flash"] = "بيانات الدخول غير صحيحة"
        return RedirectResponse(url="/login", status_code=303)
    if user["role"] != "admin":
        request.session["flash"] = "الدخول متاح فقط للإدارة"
        return RedirectResponse(url="/login", status_code=303)

    response = RedirectResponse(url="/dashboard", status_code=303)
    login_user(response, user["id"])
    return response


@app.get("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    logout_user(response)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse):
        return user
    conn = get_db()
    stats = conn.execute(
        "SELECT COUNT(*) as total_attempts, SUM(is_correct) as total_correct FROM attempts WHERE user_id = ?",
        (user["id"],),
    ).fetchone()
    leaderboard = conn.execute(
        "SELECT id, username, full_name, points FROM users WHERE role != 'admin' ORDER BY points DESC, created_at ASC LIMIT 10"
    ).fetchall()
    rank_row = conn.execute(
        "SELECT COUNT(*) + 1 AS rank FROM users WHERE role != 'admin' AND points > ?",
        (user["points"],),
    ).fetchone()
    conn.close()

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "stats": stats, "leaderboard": leaderboard, "rank": rank_row["rank"], "flash": request.session.pop("flash", None)},
    )


@app.get("/subjects/{subject_id}", response_class=HTMLResponse)
def subject_view(request: Request, subject_id: int, exam: Optional[str] = None, source: str = "past", q: Optional[str] = None, page: int = 1):
    user = get_current_user(request)
    conn = get_db()
    subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    if not subject:
        conn.close()
        return RedirectResponse(url="/", status_code=303)

    if source not in ("past", "ai"):
        source = "past"
    if source == "past":
        if exam not in ("mid", "final", "both"):
            conn.close()
            return RedirectResponse(url="/questions/past", status_code=303)
    else:
        exam = None
    per_page = 50
    offset = (page - 1) * per_page
    base_query = "FROM questions WHERE subject_id = ?"
    params = [subject_id]
    if exam and exam != "both":
        base_query += " AND exam_type = ?"
        params.append(exam)
    base_query += " AND source = ?"
    params.append(source)
    if q:
        base_query += " AND question_text LIKE ?"
        params.append(f"%{q}%")

    total = conn.execute(f"SELECT COUNT(*) {base_query}", params).fetchone()[0]
    questions = conn.execute(
        f"SELECT * {base_query} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    conn.close()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(
        "subject.html",
        {"request": request, "user": user, "subject": subject, "questions": questions, "exam": exam or "", "source": source, "q": q or "", "page": page, "total_pages": total_pages, "flash": request.session.pop("flash", None)},
    )


@app.get("/questions/{question_id}", response_class=HTMLResponse)
def question_view(request: Request, question_id: int):
    user = get_current_user(request)
    conn = get_db()
    q = conn.execute(
        "SELECT q.*, s.name AS subject_name FROM questions q JOIN subjects s ON s.id = q.subject_id WHERE q.id = ?",
        (question_id,),
    ).fetchone()
    prev_q = None
    next_q = None
    if q:
        prev_q = conn.execute(
            "SELECT id FROM questions WHERE subject_id = ? AND exam_type = ? AND source = ? AND id < ? ORDER BY id DESC LIMIT 1",
            (q["subject_id"], q["exam_type"], q["source"], q["id"]),
        ).fetchone()
        next_q = conn.execute(
            "SELECT id FROM questions WHERE subject_id = ? AND exam_type = ? AND source = ? AND id > ? ORDER BY id ASC LIMIT 1",
            (q["subject_id"], q["exam_type"], q["source"], q["id"]),
        ).fetchone()
    conn.close()
    if not q:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "question.html",
        {"request": request, "user": user, "q": q, "prev_id": prev_q["id"] if prev_q else None, "next_id": next_q["id"] if next_q else None, "flash": request.session.pop("flash", None)},
    )


@app.post("/questions/{question_id}/answer")
def answer_question(request: Request, question_id: int, choice: str = Form(...)):
    user = get_current_user(request)

    conn = get_db()
    q = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if not q:
        conn.close()
        return RedirectResponse(url="/", status_code=303)

    is_correct = 1 if choice == q["correct_choice"] else 0

    if not user:
        prev_q = conn.execute(
            "SELECT id FROM questions WHERE subject_id = ? AND exam_type = ? AND source = ? AND id < ? ORDER BY id DESC LIMIT 1",
            (q["subject_id"], q["exam_type"], q["source"], q["id"]),
        ).fetchone()
        next_q = conn.execute(
            "SELECT id FROM questions WHERE subject_id = ? AND exam_type = ? AND source = ? AND id > ? ORDER BY id ASC LIMIT 1",
            (q["subject_id"], q["exam_type"], q["source"], q["id"]),
        ).fetchone()
        conn.close()
        attempt = {"is_correct": is_correct, "chosen_choice": choice}
        return templates.TemplateResponse(
            "question_result.html",
            {
                "request": request,
                "user": None,
                "q": q,
                "attempt": attempt,
                "prev_id": prev_q["id"] if prev_q else None,
                "next_id": next_q["id"] if next_q else None,
                "flash": request.session.pop("flash", None),
            },
        )

    already_correct = conn.execute(
        "SELECT 1 FROM attempts WHERE user_id = ? AND question_id = ? AND is_correct = 1 LIMIT 1",
        (user["id"], question_id),
    ).fetchone()

    conn.execute(
        "INSERT INTO attempts (user_id, question_id, chosen_choice, is_correct, created_at) VALUES (?, ?, ?, ?, ?)",
        (user["id"], question_id, choice, is_correct, now_iso()),
    )

    if is_correct and not already_correct:
        conn.execute("UPDATE users SET points = points + 1 WHERE id = ?", (user["id"],))

    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/questions/{question_id}/result", status_code=303)


@app.get("/questions/{question_id}/result", response_class=HTMLResponse)
def question_result(request: Request, question_id: int):
    user = get_current_user(request)

    conn = get_db()
    q = conn.execute(
        "SELECT q.*, s.name AS subject_name FROM questions q JOIN subjects s ON s.id = q.subject_id WHERE q.id = ?",
        (question_id,),
    ).fetchone()
    if not q:
        conn.close()
        return RedirectResponse(url="/", status_code=303)
    prev_q = conn.execute(
        "SELECT id FROM questions WHERE subject_id = ? AND exam_type = ? AND source = ? AND id < ? ORDER BY id DESC LIMIT 1",
        (q["subject_id"], q["exam_type"], q["source"], q["id"]),
    ).fetchone()
    next_q = conn.execute(
        "SELECT id FROM questions WHERE subject_id = ? AND exam_type = ? AND source = ? AND id > ? ORDER BY id ASC LIMIT 1",
        (q["subject_id"], q["exam_type"], q["source"], q["id"]),
    ).fetchone()
    attempt = None
    if user:
        attempt = conn.execute(
            "SELECT * FROM attempts WHERE user_id = ? AND question_id = ? ORDER BY id DESC LIMIT 1",
            (user["id"], question_id),
        ).fetchone()
    conn.close()

    return templates.TemplateResponse(
        "question_result.html",
        {"request": request, "user": user, "q": q, "attempt": attempt, "prev_id": prev_q["id"] if prev_q else None, "next_id": next_q["id"] if next_q else None, "flash": request.session.pop("flash", None)},
    )


@app.post("/questions/{question_id}/report")
def report_question(request: Request, question_id: int, report_text: str = Form(...), proposed_correct_choice: Optional[str] = Form(None), proposed_explanation: Optional[str] = Form(None)):
    user = get_current_user(request)
    conn = get_db()
    conn.execute(
        "INSERT INTO reports (user_id, question_id, report_text, proposed_correct_choice, proposed_explanation, status, created_at) VALUES (?, ?, ?, ?, ?, 'new', ?)",
        (user["id"] if user else None, question_id, report_text, proposed_correct_choice, proposed_explanation, now_iso()),
    )
    conn.commit()
    conn.close()
    request.session["flash"] = "تم إرسال البلاغ"
    return RedirectResponse(url=f"/questions/{question_id}", status_code=303)


@app.get("/contact", response_class=HTMLResponse)
def contact_get(request: Request):
    user = get_current_user(request)
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()
    conn.close()
    return templates.TemplateResponse("contact.html", {"request": request, "user": user, "subjects": subjects, "flash": request.session.pop("flash", None)})


@app.post("/contact/suggest")
def contact_suggest(request: Request, subject_id: Optional[str] = Form(None), subject_name: Optional[str] = Form(None), exam_type: Optional[str] = Form(None), question_text: Optional[str] = Form(None), choice_a: Optional[str] = Form(None), choice_b: Optional[str] = Form(None), choice_c: Optional[str] = Form(None), choice_d: Optional[str] = Form(None), proposed_correct_choice: Optional[str] = Form(None), proposed_explanation: Optional[str] = Form(None)):
    user = get_current_user(request)
    conn = get_db()
    conn.execute(
        "INSERT INTO suggestions (user_id, type, subject_name, subject_id, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, proposed_correct_choice, proposed_explanation, image_path, status, created_at) VALUES (?, 'question', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)",
        (user["id"] if user else None, subject_name, subject_id or None, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, proposed_correct_choice, proposed_explanation, None, now_iso()),
    )
    conn.commit()
    conn.close()
    request.session["flash"] = "تم إرسال الاقتراح"
    return RedirectResponse(url="/contact", status_code=303)


@app.post("/contact/message")
def contact_message(request: Request, message: str = Form(...)):
    user = get_current_user(request)
    conn = get_db()
    conn.execute(
        "INSERT INTO suggestions (user_id, type, message, status, created_at) VALUES (?, 'message', ?, 'new', ?)",
        (user["id"] if user else None, message, now_iso()),
    )
    conn.commit()
    conn.close()
    request.session["flash"] = "تم إرسال الرسالة"
    return RedirectResponse(url="/contact", status_code=303)

# ---------- Admin ----------

@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()
    subject_counts = conn.execute(
        """
        SELECT s.id, COUNT(q.id) AS qcount
        FROM subjects s
        LEFT JOIN questions q ON q.subject_id = s.id
        GROUP BY s.id
        """
    ).fetchall()
    subject_count_map = {row["id"]: row["qcount"] for row in subject_counts}
    total_questions = conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
    total_subjects = conn.execute("SELECT COUNT(*) AS c FROM subjects").fetchone()["c"]
    new_suggestions = conn.execute("SELECT COUNT(*) AS c FROM suggestions WHERE status = 'new'").fetchone()["c"]
    new_reports = conn.execute("SELECT COUNT(*) AS c FROM reports WHERE status = 'new'").fetchone()["c"]
    suggestions = conn.execute("SELECT * FROM suggestions ORDER BY created_at DESC").fetchall()
    reports = conn.execute(
        "SELECT r.*, q.question_text FROM reports r JOIN questions q ON q.id = r.question_id ORDER BY r.created_at DESC"
    ).fetchall()
    questions = conn.execute(
        "SELECT q.*, s.name AS subject_name FROM questions q JOIN subjects s ON s.id = q.subject_id ORDER BY q.id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "subjects": subjects,
            "subject_count_map": subject_count_map,
            "total_questions": total_questions,
            "total_subjects": total_subjects,
            "new_suggestions": new_suggestions,
            "new_reports": new_reports,
            "suggestions": suggestions,
            "reports": reports,
            "questions": questions,
            "flash": request.session.pop("flash", None),
        },
    )


@app.get("/admin/questions/{question_id}/edit", response_class=HTMLResponse)
def admin_question_edit(request: Request, question_id: int):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    q = conn.execute(
        "SELECT q.*, s.name AS subject_name FROM questions q JOIN subjects s ON s.id = q.subject_id WHERE q.id = ?",
        (question_id,),
    ).fetchone()
    conn.close()
    if not q:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        "question_edit.html",
        {"request": request, "user": admin, "q": q, "flash": request.session.pop("flash", None)},
    )


@app.post("/admin/subjects/create")
def admin_subject_create(request: Request, name: str = Form(...)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    try:
        conn.execute("INSERT INTO subjects (name, created_at) VALUES (?, ?)", (name.strip(), now_iso()))
        conn.commit()
        request.session["flash"] = "تم إنشاء المادة"
    except sqlite3.IntegrityError:
        request.session["flash"] = "اسم المادة موجود بالفعل"
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/subjects/{subject_id}/delete")
def admin_subject_delete(request: Request, subject_id: int):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()
    conn.close()
    request.session["flash"] = "تم حذف المادة"
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/questions/create")
def admin_question_create(request: Request, subject_id: int = Form(...), exam_type: str = Form(...), source: str = Form("past"), question_text: str = Form(""), choice_a: str = Form(...), choice_b: str = Form(...), choice_c: str = Form(...), choice_d: str = Form(...), correct_choice: str = Form(...), explanation: Optional[str] = Form(None), image: UploadFile = File(None)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    image_path = save_upload_image(image)
    if source not in ("past", "ai"):
        source = "past"
    conn.execute(
        "INSERT INTO questions (subject_id, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, image_path, source, explanation, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (subject_id, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, image_path, source, explanation, now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()
    request.session["flash"] = "تم إضافة السؤال"
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/questions/{question_id}/update")
def admin_question_update(request: Request, question_id: int, question_text: str = Form(""), source: str = Form("past"), choice_a: str = Form(...), choice_b: str = Form(...), choice_c: str = Form(...), choice_d: str = Form(...), correct_choice: str = Form(...), explanation: Optional[str] = Form(None), image: UploadFile = File(None)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    image_path = save_upload_image(image)
    if source not in ("past", "ai"):
        source = "past"
    if image_path:
        conn.execute(
            "UPDATE questions SET question_text = ?, choice_a = ?, choice_b = ?, choice_c = ?, choice_d = ?, correct_choice = ?, image_path = ?, source = ?, explanation = ?, updated_at = ? WHERE id = ?",
            (question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, image_path, source, explanation, now_iso(), question_id),
        )
    else:
        conn.execute(
            "UPDATE questions SET question_text = ?, choice_a = ?, choice_b = ?, choice_c = ?, choice_d = ?, correct_choice = ?, source = ?, explanation = ?, updated_at = ? WHERE id = ?",
            (question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, source, explanation, now_iso(), question_id),
        )
    conn.commit()
    conn.close()
    request.session["flash"] = "تم تحديث السؤال"
    return RedirectResponse(url=f"/admin/questions/{question_id}/edit", status_code=303)


@app.post("/admin/questions/{question_id}/delete")
def admin_question_delete(request: Request, question_id: int):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()
    request.session["flash"] = "تم حذف السؤال"
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/suggestions/{suggestion_id}/publish")
def admin_publish_suggestion(request: Request, suggestion_id: int, subject_id: int = Form(...), exam_type: str = Form(...)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    sug = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    if not sug:
        conn.close()
        request.session["flash"] = "الاقتراح غير موجود"
        return RedirectResponse(url="/admin", status_code=303)

    conn.execute(
        "INSERT INTO questions (subject_id, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, image_path, source, explanation, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (subject_id, exam_type, sug["question_text"] or "", sug["choice_a"] or "", sug["choice_b"] or "", sug["choice_c"] or "", sug["choice_d"] or "", sug["proposed_correct_choice"] or "A", sug["image_path"], "past", sug["proposed_explanation"], now_iso(), now_iso()),
    )
    conn.execute("UPDATE suggestions SET status = 'published' WHERE id = ?", (suggestion_id,))
    conn.commit()
    conn.close()
    request.session["flash"] = "تم نشر الاقتراح كسؤال"
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/suggestions/{suggestion_id}/reject")
def admin_reject_suggestion(request: Request, suggestion_id: int):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    conn.execute("DELETE FROM suggestions WHERE id = ?", (suggestion_id,))
    conn.commit()
    conn.close()
    request.session["flash"] = "تم حذف الاقتراح"
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/reports/{report_id}/resolve")
def admin_resolve_report(request: Request, report_id: int, correct_choice: str = Form(...), explanation: Optional[str] = Form(None)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    conn = get_db()
    rep = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not rep:
        conn.close()
        request.session["flash"] = "البلاغ غير موجود"
        return RedirectResponse(url="/admin", status_code=303)

    conn.execute("UPDATE questions SET correct_choice = ?, explanation = ?, updated_at = ? WHERE id = ?", (correct_choice, explanation, now_iso(), rep["question_id"]))
    conn.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()
    request.session["flash"] = "تم تصحيح السؤال وحل البلاغ"
    return RedirectResponse(url="/admin", status_code=303)


# ---------- Export / Import ----------

@app.get("/admin/export.csv")
def admin_export_csv(request: Request):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    conn = get_db()
    rows = conn.execute(
        "SELECT q.id, s.name AS subject, q.exam_type, q.question_text, q.choice_a, q.choice_b, q.choice_c, q.choice_d, q.correct_choice, q.image_path, q.source, q.explanation FROM questions q JOIN subjects s ON s.id = q.subject_id ORDER BY q.id ASC"
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "subject", "exam_type", "question_text", "choice_a", "choice_b", "choice_c", "choice_d", "correct_choice", "image_path", "source", "explanation"])
    for r in rows:
        writer.writerow([r["id"], r["subject"], r["exam_type"], r["question_text"], r["choice_a"], r["choice_b"], r["choice_c"], r["choice_d"], r["correct_choice"], r["image_path"], r["source"], r["explanation"]])

    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=questions.csv"})


@app.post("/admin/import.csv")
def admin_import_csv(request: Request, file: UploadFile = File(...)):
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin

    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    conn = get_db()
    for row in reader:
        subject_name = row.get("subject")
        if not subject_name:
            continue
        subject = conn.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,)).fetchone()
        if not subject:
            conn.execute("INSERT INTO subjects (name, created_at) VALUES (?, ?)", (subject_name, now_iso()))
            subject = conn.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,)).fetchone()
        conn.execute(
            "INSERT INTO questions (subject_id, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, image_path, source, explanation, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (subject["id"], row.get("exam_type", "mid"), row.get("question_text", ""), row.get("choice_a", ""), row.get("choice_b", ""), row.get("choice_c", ""), row.get("choice_d", ""), row.get("correct_choice", "A"), row.get("image_path", None), row.get("source", "past"), row.get("explanation", ""), now_iso(), now_iso()),
        )
    conn.commit()
    conn.close()
    request.session["flash"] = "تم استيراد الأسئلة"
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/404", response_class=HTMLResponse)
def not_found(request: Request):
    return templates.TemplateResponse("404.html", {"request": request, "flash": request.session.pop("flash", None)})


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    webbrowser.open("http://127.0.0.1:8000")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

