from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime
import os
import json
import sqlite3
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer
import smtplib
from email.message import EmailMessage

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "supersecretkey"
serializer = URLSafeTimedSerializer(app.secret_key)

ADMIN_TIMEOUT_SECONDS = 30 * 60       # 30 minutes
VOLUNTEER_TIMEOUT_SECONDS = 30 * 60   # 30 minutes


def require_admin():
    if not session.get("admin_verified"):
        return redirect(url_for("menu"))


@app.before_request
def refresh_session_timeouts():
    now_ts = datetime.now().timestamp()

    if session.get("admin_verified"):
        last = session.get("admin_last_seen")
        if last is not None and now_ts - last > ADMIN_TIMEOUT_SECONDS:
            session.pop("admin_verified", None)
            session.pop("admin_email", None)
            session.pop("admin_last_seen", None)
        else:
            session["admin_last_seen"] = now_ts

    if session.get("email_verified"):
        last = session.get("email_last_seen")
        if last is not None and now_ts - last > VOLUNTEER_TIMEOUT_SECONDS:
            session.pop("email_verified", None)
            session.pop("verified_email", None)
            session.pop("email_last_seen", None)
        else:
            session["email_last_seen"] = now_ts


# --- SQLite setup ---
DB_FILE = "volunteers.db"


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


# --- File uploads ---
STATIC_FOLDER = "static"
os.makedirs(STATIC_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = STATIC_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def dictify_rows(rows):
    return [dict(row) for row in rows]


def generate_activation_token(email: str) -> str:
    return serializer.dumps(email, salt="email-activate")


def confirm_activation_token(token: str, max_age: int = 3600) -> str | None:
    try:
        email = serializer.loads(token, salt="email-activate", max_age=max_age)
    except Exception:
        return None
    return email


def send_activation_email(recipient_email: str) -> None:
    token = generate_activation_token(recipient_email)
    activation_link = url_for("activate_email", token=token, _external=True)

    subject = "KRAS Kickers volunteer email verification"
    body = f"""Thank you for your interest in volunteering with KRAS Kickers.

To continue with your volunteer application, confirm your email by clicking this link:

{activation_link}

If you did not request this, you can ignore this message.
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "no-reply@kraskickers.org")
    msg["To"] = recipient_email
    msg.set_content(body)

    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_user and smtp_password:
            server.starttls()
            server.login(smtp_user, smtp_password)
        server.send_message(msg)


def send_admin_activation_email(recipient_email: str) -> None:
    token = generate_activation_token(recipient_email)
    activation_link = url_for("admin_activate", token=token, _external=True)

    subject = "KRAS Kickers admin access verification"
    body = f"""You requested admin access to the KRAS Kickers volunteer system.

To continue, confirm your KRAS Kickers admin email by clicking this link:

{activation_link}

If you did not request this, please ignore this message.
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "no-reply@kraskickers.org")
    msg["To"] = recipient_email
    msg.set_content(body)

    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_user and smtp_password:
            server.starttls()
            server.login(smtp_user, smtp_password)
        server.send_message(msg)


# --- Shared POST handler for volunteer application submissions ---
def _handle_application_post():
    form_data = request.form.to_dict()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    form_email = (form_data.get("email") or "").strip().lower()
    verified_email = (session.get("verified_email") or "").strip().lower()

    if not form_email:
        form_email = verified_email

    if not session.get("email_verified") or not form_email or form_email != verified_email:
        return jsonify(
            {
                "status": "error",
                "message": "Please verify your email before submitting the application.",
            }
        ), 400

    status = "Pending"
    history_list = [
        {
            "event": "Application submitted",
            "timestamp": timestamp,
        }
    ]
    notes_list = []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO applications
        (first_name, last_name, email, phone, contact, title, time, duration, location, comments, status, timestamp, history, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            form_data.get("first_name"),
            form_data.get("last_name"),
            form_email,
            form_data.get("phone"),
            form_data.get("contact"),
            form_data.get("title"),
            form_data.get("time"),
            form_data.get("duration"),
            form_data.get("location"),
            form_data.get("comments"),
            status,
            timestamp,
            json.dumps(history_list),
            json.dumps(notes_list),
        ),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "status": "success",
            "message": "Application submitted successfully!",
            "title": form_data.get("title", "Volunteer Opportunity"),
        }
    )


@app.route("/activate/<token>")
def activate_email(token):
    email = confirm_activation_token(token)
    if not email:
        return "Activation link is invalid or expired", 400

    session["email_verified"] = True
    session["verified_email"] = email
    session["email_last_seen"] = datetime.now().timestamp()

    return redirect(url_for("index", verified=1))


# --- HOME PAGE (Volunteer Opportunities + Application Form) ---
@app.route("/", methods=["GET", "POST"])
def index():
    verified_flag = request.args.get("verified")

    if request.method == "GET" and verified_flag != "1":
        session.pop("email_verified", None)
        session.pop("verified_email", None)
        session.pop("email_last_seen", None)

    if request.method == "POST":
        return _handle_application_post()

    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM opportunities WHERE closed = 0 OR closed IS NULL"
    ).fetchall()
    conn.close()
    opportunities = dictify_rows(rows)

    for opp in opportunities:
        tags_raw = opp.get("tags")
        if isinstance(tags_raw, str) and tags_raw.strip():
            try:
                opp["tags"] = json.loads(tags_raw)
            except json.JSONDecodeError:
                opp["tags"] = []
        elif tags_raw is None:
            opp["tags"] = []
        opp["frequency"] = opp.get("mode", "")

    return render_template("index.html", opportunities=opportunities)


# --- Manage Active Opportunities ---
@app.route("/manage", methods=["GET"])
def manage():
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM opportunities WHERE closed = 0 OR closed IS NULL"
    ).fetchall()
    conn.close()
    opportunities = dictify_rows(rows)

    for opp in opportunities:
        tags_raw = opp.get("tags")
        if isinstance(tags_raw, str) and tags_raw.strip():
            try:
                opp["tags"] = json.loads(tags_raw)
            except json.JSONDecodeError:
                opp["tags"] = []
        elif tags_raw is None:
            opp["tags"] = []
        opp["frequency"] = opp.get("mode", "")

    return render_template("manage.html", opportunities=opportunities)


# --- Add New Opportunity ---
@app.route("/add", methods=["POST"])
def add_opportunity():
    auth = require_admin()
    if auth:
        return auth
    image_path = ""
    if "image" in request.files:
        file = request.files["image"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename).replace(" ", "_").lower()
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            image_path = filename

    tags_json = request.form.get("tags_json") or request.form.get("tags") or "[]"
    try:
        tags = json.loads(tags_json)
    except Exception:
        tags = []
    tags_json = json.dumps(tags)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO opportunities
        (title, time, duration, mode, description, requirements, location, image, tags, closed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            request.form.get("title"),
            request.form.get("time", ""),
            request.form.get("duration", ""),
            request.form.get("mode", ""),
            request.form.get("desc", ""),
            request.form.get("requirements", ""),
            request.form.get("location", ""),
            image_path if image_path else "default.png",
            tags_json,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Opportunity added successfully!"})


# --- Update Opportunity ---
@app.route("/update/<int:opp_id>", methods=["POST"])
def update_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()

    tags_json = request.form.get("tags_json") or request.form.get("tags") or "[]"
    try:
        tags = json.loads(tags_json)
    except Exception:
        tags = []
    tags_json = json.dumps(tags)

    cur.execute(
        """
        UPDATE opportunities
        SET title = ?, time = ?, duration = ?, mode = ?, description = ?,
            requirements = ?, location = ?, tags = ?
        WHERE id = ?
        """,
        (
            request.form.get("title"),
            request.form.get("time", ""),
            request.form.get("duration", ""),
            request.form.get("mode", ""),
            request.form.get("desc", ""),
            request.form.get("requirements", ""),
            request.form.get("location", ""),
            tags_json,
            opp_id,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Opportunity updated successfully!"})


# --- Delete Opportunity ---
@app.route("/delete/<int:opp_id>", methods=["POST"])
def delete_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity deleted"})


# --- Menu Page ---
@app.route("/menu")
def menu():
    return render_template("Menu.html")


@app.route("/admin_request_access", methods=["POST"])
def admin_request_access():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email.endswith("@kraskickers.org"):
        return jsonify({"error": "Admin access requires a @kraskickers.org email address."}), 400

    send_admin_activation_email(email)
    return jsonify({"message": "A verification link has been sent to your KRAS Kickers email."})


@app.route("/admin_activate/<token>")
def admin_activate(token):
    email = confirm_activation_token(token, max_age=3600)
    if not email or not email.endswith("@kraskickers.org"):
        return "Invalid or expired admin activation link.", 400

    session["admin_verified"] = True
    session["admin_email"] = email
    session["admin_last_seen"] = datetime.now().timestamp()

    return redirect(url_for("menu", admin_verified=1))


# --- Close / Reopen Opportunity ---
@app.route("/close_opportunity/<int:opp_id>", methods=["POST"])
def close_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()
    closed_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur.execute(
        "UPDATE opportunities SET closed = 1, closed_date = ? WHERE id = ?",
        (closed_date, opp_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity closed"})


@app.route("/reopen_opportunity/<int:opp_id>", methods=["POST"])
def reopen_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE opportunities SET closed = 0, closed_date = NULL WHERE id = ?",
        (opp_id,),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity reopened"})


# --- Closed Opportunities ---
@app.route("/closed")
def closed_opportunities():
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    opp_rows = conn.execute("SELECT * FROM opportunities WHERE closed = 1").fetchall()
    apps_rows = conn.execute("SELECT * FROM applications").fetchall()
    conn.close()

    opportunities = dictify_rows(opp_rows)
    applications = dictify_rows(apps_rows)

    for opp in opportunities:
        tags_raw = opp.get("tags")
        if isinstance(tags_raw, str) and tags_raw.strip():
            try:
                opp["tags"] = json.loads(tags_raw)
            except json.JSONDecodeError:
                opp["tags"] = []
        elif tags_raw is None:
            opp["tags"] = []
        opp["frequency"] = opp.get("mode", "")

    return render_template(
        "closed.html", opportunities=opportunities, applications=applications
    )


# --- Applicants per Opportunity ---
@app.route("/applicants/<int:opp_id>")
def applicants(opp_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()

    opp_row = cur.execute(
        "SELECT * FROM opportunities WHERE id = ?", (opp_id,)
    ).fetchone()
    applicants_rows = cur.execute(
        "SELECT * FROM applications WHERE opportunity_id = ? ORDER BY timestamp DESC",
        (opp_id,),
    ).fetchall()
    conn.close()

    opportunity = dict(opp_row) if opp_row else {}
    tags_raw = opportunity.get("tags")
    if isinstance(tags_raw, str) and tags_raw.strip():
        try:
            opportunity["tags"] = json.loads(tags_raw)
        except json.JSONDecodeError:
            opportunity["tags"] = []
    elif tags_raw is None:
        opportunity["tags"] = []
    opportunity["frequency"] = opportunity.get("mode", "")

    applicants = dictify_rows(applicants_rows)

    return render_template(
        "applicants.html", opportunity=opportunity, applicants=applicants
    )


# --- Volunteer Check-In (used by index page) ---
@app.route("/check")
def check_volunteer():
    """
    Check whether a volunteer already exists (by email).
    Always sends a verification email and returns any approved assignments
    only after the email has been verified for this session.
    """

    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({
            "exists": False,
            "first_name": "",
            "last_name": "",
            "email": "",
            "phone": "",
            "assignments": [],
            "activation_message": "",
        }), 200

    conn = sqlite3.connect("volunteers.db")
    conn.row_factory = sqlite3.Row

    try:
        person_row = conn.execute(
            """
            SELECT
                first_name,
                last_name,
                email,
                phone
            FROM applications
            WHERE LOWER(email) = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (email,),
        ).fetchone()

        assignment_rows = []
        if person_row:
            assignment_rows = conn.execute(
                """
                SELECT
                    a.timestamp AS submitted_at,
                    a.title,
                    o.time        AS time_commitment,
                    o.duration    AS duration,
                    o.mode        AS frequency,
                    o.location    AS location
                FROM applications a
                JOIN opportunities o ON a.opportunity_id = o.id
                WHERE
                    LOWER(a.email) = ?
                    AND a.status = "Assigned"
                ORDER BY a.timestamp DESC
                """,
                (email,),
            ).fetchall()

        session_email = (session.get("verified_email") or "").strip().lower()
        session_verified = bool(session.get("email_verified"))

        resp = {
            "exists": bool(person_row),
            "first_name": person_row["first_name"] if person_row else "",
            "last_name": person_row["last_name"] if person_row else "",
            "email": person_row["email"] if person_row else email,
            "phone": person_row["phone"] if person_row else "",
            "assignments": [],
            "activation_message": "",
        }

        if not (session_verified and session_email == email):
            send_activation_email(email)
            resp["activation_message"] = (
                "We just sent a verification email. Please click the link in that email "
                "so you can view your approved opportunities and submit your application."
            )
        else:
            if assignment_rows:
                assignments = [
                    {
                        "submitted_at": row["submitted_at"],
                        "title": row["title"],
                        "time_commitment": row["time_commitment"],
                        "duration": row["duration"],
                        "frequency": row["frequency"],
                        "location": row["location"],
                    }
                    for row in assignment_rows
                ]
                resp["assignments"] = assignments

        return jsonify(resp), 200

    finally:
        conn.close()


# --- Review and Assignments ---
@app.route("/review")
def review():
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM applications ORDER BY timestamp DESC"
    ).fetchall()
    conn.close()
    applications = dictify_rows(rows)

    for app_entry in applications:
        history_raw = app_entry.get("history")
        if isinstance(history_raw, str) and history_raw.strip():
            try:
                app_entry["history"] = json.loads(history_raw)
            except json.JSONDecodeError:
                app_entry["history"] = []
        else:
            app_entry["history"] = []

        notes_raw = app_entry.get("notes")
        if isinstance(notes_raw, str) and notes_raw.strip():
            try:
                app_entry["notes"] = json.loads(notes_raw)
            except json.JSONDecodeError:
                app_entry["notes"] = []
        else:
            app_entry["notes"] = []

    return render_template("review.html", applications=applications)


# --- Update Application Status / Assign to Opportunity ---
@app.route("/update_status/<int:app_id>", methods=["POST"])
def update_status(app_id):
    auth = require_admin()
    if auth:
        return auth
    new_status = request.form.get("status", "Pending")
    opportunity_id = request.form.get("opportunity_id")
    note_text = request.form.get("note", "").strip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    cur = conn.cursor()

    app_row = cur.execute(
        "SELECT status, history, notes FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not app_row:
        conn.close()
        return jsonify({"error": "Application not found"}), 404

    try:
        history_list = json.loads(app_row["history"]) if app_row["history"] else []
    except json.JSONDecodeError:
        history_list = []

    try:
        notes_list = json.loads(app_row["notes"]) if app_row["notes"] else []
    except json.JSONDecodeError:
        notes_list = []

    history_list.append(
        {
            "event": f"Status changed to '{new_status}'",
            "timestamp": timestamp,
        }
    )

    if note_text:
        notes_list.append(
            {
                "timestamp": timestamp,
                "note": note_text,
            }
        )

    cur.execute(
        """
        UPDATE applications
        SET status = ?, opportunity_id = ?, history = ?, notes = ?
        WHERE id = ?
        """,
        (
            new_status,
            opportunity_id if opportunity_id else None,
            json.dumps(history_list),
            json.dumps(notes_list),
            app_id,
        ),
    )

    conn.commit()
    conn.close()
    return jsonify({"message": "Status updated successfully"})


# --- Delete Application ---
@app.route("/delete_application/<int:app_id>", methods=["POST"])
def delete_application(app_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Application deleted"})


# --- Volunteers Overview ---
@app.route("/volunteers")
def volunteers():
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM applications ORDER BY timestamp DESC"
    ).fetchall()
    conn.close()
    applications = dictify_rows(rows)

    for app_entry in applications:
        history_raw = app_entry.get("history")
        if isinstance(history_raw, str) and history_raw.strip():
            try:
                app_entry["history"] = json.loads(history_raw)
            except json.JSONDecodeError:
                app_entry["history"] = []
        else:
            app_entry["history"] = []

        notes_raw = app_entry.get("notes")
        if isinstance(notes_raw, str) and notes_raw.strip():
            try:
                app_entry["notes"] = json.loads(notes_raw)
            except json.JSONDecodeError:
                app_entry["notes"] = []
        else:
            app_entry["notes"] = []

    return render_template("volunteers.html", applications=applications)


# --- Volunteer Detail Page ---
@app.route("/volunteer/<int:app_id>")
def volunteer(app_id):
    auth = require_admin()
    if auth:
        return auth
    conn = get_db_connection()
    cur = conn.cursor()

    app_row = cur.execute(
        "SELECT * FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not app_row:
        conn.close()
        return "Volunteer application not found", 404

    apps_rows = cur.execute(
        "SELECT * FROM applications WHERE email = ? ORDER BY timestamp DESC",
        (app_row["email"],),
    ).fetchall()
    conn.close()

    application = dict(app_row)
    history_raw = application.get("history")
    if isinstance(history_raw, str) and history_raw.strip():
        try:
            application["history"] = json.loads(history_raw)
        except json.JSONDecodeError:
            application["history"] = []
    else:
        application["history"] = []

    notes_raw = application.get("notes")
    if isinstance(notes_raw, str) and notes_raw.strip():
        try:
            application["notes"] = json.loads(notes_raw)
        except json.JSONDecodeError:
            application["notes"] = []
    else:
        application["notes"] = []

    history_by_app = []
    for row in apps_rows:
        try:
            hlist = json.loads(row["history"]) if row["history"] else []
        except json.JSONDecodeError:
            hlist = []
        history_by_app.append(
            {
                "id": row["id"],
                "title": row["title"],
                "status": row["status"],
                "timestamp": row["timestamp"],
                "events": hlist,
            }
        )

    return render_template(
        "volunteer.html", application=application, history_by_app=history_by_app
    )


# --- Add Note to Application ---
@app.route("/add_note/<int:app_id>", methods=["POST"])
def add_note(app_id):
    auth = require_admin()
    if auth:
        return auth
    note_text = request.form.get("note", "").strip()
    if not note_text:
        return jsonify({"error": "Note text is required"}), 400

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    cur = conn.cursor()
    app_row = cur.execute(
        "SELECT notes FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not app_row:
        conn.close()
        return jsonify({"error": "Application not found"}), 404

    try:
        notes_list = json.loads(app_row["notes"]) if app_row["notes"] else []
    except json.JSONDecodeError:
        notes_list = []

    notes_list.append(
        {
            "timestamp": timestamp,
            "note": note_text,
        }
    )

    cur.execute(
        "UPDATE applications SET notes = ? WHERE id = ?",
        (json.dumps(notes_list), app_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Note added successfully"})


if __name__ == "__main__":
    app.run(debug=True)
