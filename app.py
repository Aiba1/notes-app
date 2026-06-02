import sqlite3
from urllib.parse import urlencode
from flask import Flask, render_template, request, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

import requests

GEMINI_API_KEY = "AIzaSyBmM7Tplq-JMTKLgkFh12lTM0hvsEPh4XI"

def ai_improve(text):
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        )

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Improve this text, keep the meaning, make it clear and polished:\n\n" + text
                        }
                    ]
                }
            ]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()

        data = response.json()

        return (
            data
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "No response")
        )

    except requests.HTTPError as error:
        print("Gemini API error:", error)
        return "AI is unavailable right now. Your note was saved without Gemini improvement: " + text

    except requests.RequestException as error:
        print("Gemini connection error:", error)
        return "Improved (offline): " + text.capitalize()

    except Exception as error:
        print("AI improve error:", error)
        return "Improved (offline): " + text.capitalize()

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        description TEXT,
        avatar TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        folder_id INTEGER,
        content TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT
    )""")

    c.execute("PRAGMA table_info(notes)")
    note_columns = [column[1] for column in c.fetchall()]
    if "folder_id" not in note_columns:
        c.execute("ALTER TABLE notes ADD COLUMN folder_id INTEGER")

    conn.commit()
    conn.close()
    

app = Flask(__name__)
app.secret_key = "secret123"

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (username, password, description, avatar) VALUES (?,?,?,?)",
            (username, password, "", ""))
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=? AND password=?", (username,password))
        user = c.fetchone()
        conn.close()

        if user:
            login_user(User(user[0]))
            return redirect("/notes")

    return render_template("login.html")

@app.route("/notes", methods=["GET","POST"])
@login_required
def notes():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    folder_id = request.args.get("folder", type=int)
    search_query = request.args.get("q", "").strip()
    edit_note_id = request.args.get("edit", type=int)
    current_folder = None

    if folder_id:
        c.execute(
            "SELECT id, name FROM folders WHERE id=? AND user_id=?",
            (folder_id, current_user.id)
        )
        current_folder = c.fetchone()

        if not current_folder:
            conn.close()
            return redirect("/notes")

    if request.method == "POST":
        if "folder_name" in request.form:
            folder_name = request.form["folder_name"].strip()

            if folder_name:
                c.execute(
                    "INSERT INTO folders (user_id, name) VALUES (?,?)",
                    (current_user.id, folder_name)
                )
                conn.commit()

            conn.close()
            return redirect("/notes")

        content = request.form["content"].strip()

        if "ai" in request.form:
            content = ai_improve(content)

        if content:
            note_folder_id = current_folder[0] if current_folder else None
            c.execute(
                "INSERT INTO notes (user_id, folder_id, content) VALUES (?,?,?)",
                (current_user.id, note_folder_id, content)
            )
            conn.commit()

        redirect_url = f"/notes?folder={current_folder[0]}" if current_folder else "/notes"
        conn.close()
        return redirect(redirect_url)

    c.execute(
        """SELECT folders.id, folders.name, COUNT(notes.id)
           FROM folders
           LEFT JOIN notes ON notes.folder_id = folders.id
           WHERE folders.user_id=?
           GROUP BY folders.id, folders.name
           ORDER BY folders.id DESC""",
        (current_user.id,)
    )
    folders = c.fetchall()

    c.execute(
        "SELECT COUNT(*) FROM notes WHERE user_id=? AND folder_id IS NULL",
        (current_user.id,)
    )
    main_notes_count = c.fetchone()[0]

    if current_folder:
        if search_query:
            c.execute(
                """SELECT id, content FROM notes
                   WHERE user_id=? AND folder_id=? AND content LIKE ?
                   ORDER BY id DESC""",
                (current_user.id, current_folder[0], f"%{search_query}%")
            )
        else:
            c.execute(
                "SELECT id, content FROM notes WHERE user_id=? AND folder_id=? ORDER BY id DESC",
                (current_user.id, current_folder[0])
            )
    else:
        if search_query:
            c.execute(
                """SELECT id, content FROM notes
                   WHERE user_id=? AND folder_id IS NULL AND content LIKE ?
                   ORDER BY id DESC""",
                (current_user.id, f"%{search_query}%")
            )
        else:
            c.execute(
                "SELECT id, content FROM notes WHERE user_id=? AND folder_id IS NULL ORDER BY id DESC",
                (current_user.id,)
            )
    notes = c.fetchall()
    conn.close()

    return render_template(
        "notes.html",
        notes=notes,
        folders=folders,
        current_folder=current_folder,
        main_notes_count=main_notes_count,
        search_query=search_query,
        edit_note_id=edit_note_id
    )

@app.route("/notes/<int:note_id>/edit", methods=["POST"])
@login_required
def edit_note(note_id):
    content = request.form["content"].strip()
    folder_id = request.form.get("folder", type=int)
    search_query = request.form.get("q", "").strip()

    query_params = []
    if folder_id:
        query_params.append(("folder", folder_id))
    if search_query:
        query_params.append(("q", search_query))

    redirect_url = "/notes"
    if query_params:
        redirect_url += "?" + urlencode(query_params)

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if content:
        c.execute(
            "UPDATE notes SET content=? WHERE id=? AND user_id=?",
            (content, note_id, current_user.id)
        )
        conn.commit()

    conn.close()
    return redirect(redirect_url)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # сохранение изменений
    if request.method == "POST":
        username = request.form["username"]
        description = request.form["description"]
        avatar = request.form["avatar"]

        c.execute("""
            UPDATE users 
            SET username=?, description=?, avatar=? 
            WHERE id=?
        """, (username, description, avatar, current_user.id))

        conn.commit()
        return redirect("/profile")

    # получаем пользователя
    c.execute("SELECT username, description, avatar FROM users WHERE id=?",
              (current_user.id,))
    user = c.fetchone()

    conn.close()

    edit_mode = request.args.get("edit")

    return render_template("profile.html", user=user, edit_mode=edit_mode)



@app.route("/logout")
def logout():
    logout_user()
    return redirect("/login")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)



