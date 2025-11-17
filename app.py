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


# --- Shared POST handler for volunteer application submissions ---
def _handle_application_post():
    if not session.get("email_verified"):
        return jsonify(
            {
                "error": "Email not verified. Please check your email for the activation link."
            }
        ), 403

    form_data = request.form.to_dict()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

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
            form_data.get("email"),
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
            "message": "Application submitted successfully!",
            "title": form_data.get("title", "Volunteer Opportunity"),
        }
    )


# -----------------------------------
# Email + Token Helper Functions
# -----------------------------------

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


@app.route("/activate/<token>")
def activate_email(token):
    email = confirm_activation_token(token)
    if not email:
        return "Activation link is invalid or expired", 400

    session["email_verified"] = True
    session["verified_email"] = email
    return redirect(url_for("index"))



# --- HOME PAGE (Volunteer Opportunities + Application Form) ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        return _handle_application_post()

    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM opportunities WHERE closed = 0 OR closed IS NULL"
    ).fetchall()
    conn.close()
    opportunities = dictify_rows(rows)

    # Convert tags JSON string into Python objects for the template
    # and expose "frequency" as an alias for the DB column "mode"
    for opp in opportunities:
        tags_raw = opp.get("tags")
        if isinstance(tags_raw, str) and tags_raw.strip():
            try:
                opp["tags"] = json.loads(tags_raw)
            except json.JSONDecodeError:
                opp["tags"] = []
        elif tags_raw is None:
            opp["tags"] = []
        # alias for templates – index.html expects opp.frequency
        opp["frequency"] = opp.get("mode", "")

    return render_template("index.html", opportunities=opportunities)


# --- Manage Active Opportunities ---
@app.route("/manage", methods=["GET"])
def manage():
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
        # alias to match any template that uses opp.frequency
        opp["frequency"] = opp.get("mode", "")

    return render_template("manage.html", opportunities=opportunities)


# --- Add Opportunity ---
@app.route("/add", methods=["POST"])
def add_opportunity():
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
        (title, time, duration, mode, desc, requirements, location, image, tags, closed)
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
    return jsonify({"message": "Opportunity added!"})


# --- Update Opportunity ---
@app.route("/update/<int:opp_id>", methods=["POST"])
def update_opportunity(opp_id):
    conn = get_db_connection()
    cur = conn.cursor()

    tags_json = request.form.get("tags_json") or request.form.get("tags") or "[]"
    try:
        tags = json.loads(tags_json)
    except Exception:
        tags = []
    tags_json = json.dumps(tags)

    update_fields = (
        request.form.get("title"),
        request.form.get("time", ""),
        request.form.get("duration", ""),
        request.form.get("mode", ""),
        request.form.get("desc", ""),
        request.form.get("requirements", ""),
        request.form.get("location", ""),
        tags_json,
        opp_id,
    )

    cur.execute(
        """
        UPDATE opportunities
        SET title = ?, time = ?, duration = ?, mode = ?, desc = ?, requirements = ?, location = ?, tags = ?
        WHERE id = ?
        """,
        update_fields,
    )

    if "image" in request.files:
        file = request.files["image"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename).replace(" ", "_").lower()
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            cur.execute(
                "UPDATE opportunities SET image = ? WHERE id = ?",
                (filename, opp_id),
            )

    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity updated!"})


# --- Delete Opportunity ---
@app.route("/delete/<int:opp_id>", methods=["POST"])
def delete_opportunity(opp_id):
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


# --- Close / Reopen Opportunity ---
@app.route("/close_opportunity/<int:opp_id>", methods=["POST"])
def close_opportunity(opp_id):
    conn = get_db_connection()
    cur = conn.cursor()
    closed_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur.execute(
        "UPDATE opportunities SET closed = 1, closed_date = ? WHERE id = ?",
        (closed_date, opp_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity marked as closed."})


@app.route("/reopen_opportunity/<int:opp_id>", methods=["POST"])
def reopen_opportunity(opp_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE opportunities SET closed = 0, closed_date = NULL WHERE id = ?",
        (opp_id,),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity reopened successfully."})


# --- Closed Opportunities ---
@app.route("/closed")
def closed_opportunities():
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
        # expose frequency alias here too
        opp["frequency"] = opp.get("mode", "")

        opp["volunteers"] = [
            a for a in applications if a.get("title") == opp.get("title")
        ]

    return render_template("closed.html", opportunities=opportunities)


# --- View Applicants for a Specific Opportunity ---
@app.route("/applicants/<int:opp_id>")
def view_applicants(opp_id):
    conn = get_db_connection()
    opp_row = conn.execute(
        "SELECT * FROM opportunities WHERE id = ?", (opp_id,)
    ).fetchone()
    if opp_row is None:
        conn.close()
        return "Opportunity not found", 404

    applicants_rows = conn.execute(
        "SELECT * FROM applications WHERE title = ? ORDER BY timestamp DESC",
        (opp_row["title"],),
    ).fetchall()
    conn.close()

    opportunity = dict(opp_row)
    tags_raw = opportunity.get("tags")
    if isinstance(tags_raw, str) and tags_raw.strip():
        try:
            opportunity["tags"] = json.loads(tags_raw)
        except json.JSONDecodeError:
            opportunity["tags"] = []
    elif tags_raw is None:
        opportunity["tags"] = []
    # alias for applicants.html if it wants opportunity.frequency
    opportunity["frequency"] = opportunity.get("mode", "")

    applicants = dictify_rows(applicants_rows)

    return render_template(
        "applicants.html", opportunity=opportunity, applicants=applicants
    )


# --- Volunteer Check-In (used by index page) ---
@app.route("/check")
def check_volunteer():
    """
    Check whether a volunteer already exists (by email) and,
    in all cases, send an activation email so they can verify
    their address before submitting the application.
    """

    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"exists": False}), 200

    # Reset verification state whenever a new email is checked
    session["email_verified"] = False
    session["verified_email"] = None

    activation_message = ""
    try:
        send_activation_email(email)
        activation_message = (
            "We sent an activation link to your email. "
            "Click that link to unlock the application form."
        )
    except Exception as exc:
        activation_message = f"Could not send activation email: {exc}"

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

        if not person_row:
            # New volunteer
            return jsonify(
                {
                    "exists": False,
                    "activation_message": activation_message,
                }
            ), 200

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
            LEFT JOIN opportunities o
                ON a.title = o.title
            WHERE
                LOWER(a.email) = ?
                AND a.status = 'Assigned'
            ORDER BY a.timestamp DESC
            """,
            (email,),
        ).fetchall()

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

        resp = {
            "exists": True,
            "first_name": person_row["first_name"],
            "last_name": person_row["last_name"],
            "email": person_row["email"],
            "phone": person_row["phone"],
            "assignments": assignments,
            "activation_message": activation_message,
        }
        return jsonify(resp), 200

    finally:
        conn.close()



# --- Review and Assignments ---
@app.route("/review")
def review():
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


@app.route("/update_status/<int:app_id>", methods=["POST"])
def update_status(app_id):
    new_status = request.form.get("status", "Pending")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT history FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Application not found"}), 404

    history_raw = row["history"] or "[]"
    try:
        history_list = json.loads(history_raw)
    except json.JSONDecodeError:
        history_list = []

    history_list.append(
        {
            "event": f"Status updated to {new_status}",
            "timestamp": ts,
        }
    )

    cur.execute(
        """
        UPDATE applications
        SET status = ?, history = ?
        WHERE id = ?
        """,
        (new_status, json.dumps(history_list), app_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Status updated successfully"})


@app.route("/delete_application/<int:app_id>", methods=["POST"])
def delete_application(app_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Application deleted successfully."})




# --- Volunteers Overview ---
@app.route("/volunteers")
def volunteers():
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


# --- Volunteer Detail ---
@app.route("/volunteer/<int:app_id>")
def volunteer_detail(app_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?",
        (app_id,)
    ).fetchone()

    if not row:
        conn.close()
        return "Volunteer not found", 404

    app_entry = dict(row)

    # Parse history JSON
    history_raw = app_entry.get("history")
    if isinstance(history_raw, str) and history_raw.strip():
        try:
            app_entry["history"] = json.loads(history_raw)
        except json.JSONDecodeError:
            app_entry["history"] = []
    else:
        app_entry["history"] = []

    # Parse notes JSON
    notes_raw = app_entry.get("notes")
    if isinstance(notes_raw, str) and notes_raw.strip():
        try:
            app_entry["notes"] = json.loads(notes_raw)
        except json.JSONDecodeError:
            app_entry["notes"] = []
    else:
        app_entry["notes"] = []

    # Find the opportunity this application belongs to,
    # so we can send the user back to its Applicants page.
    opp_row = conn.execute(
        "SELECT id FROM opportunities WHERE title = ?",
        (app_entry.get("title", ""),)
    ).fetchone()
    conn.close()

    back_opp_id = opp_row["id"] if opp_row else None

    return render_template(
        "review_detail.html",
        app=app_entry,
        back_opp_id=back_opp_id,
    )



# --- Admin Notes ---
@app.route("/add_note/<int:app_id>", methods=["POST"])
def add_note(app_id):
    note_text = request.form.get("note", "").strip()
    if not note_text:
        return jsonify({"error": "Note text is required"}), 400

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT notes, history FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Application not found"}), 404

    notes_raw = row["notes"] or "[]"
    history_raw = row["history"] or "[]"

    try:
        notes_list = json.loads(notes_raw)
    except json.JSONDecodeError:
        notes_list = []

    try:
        history_list = json.loads(history_raw)
    except json.JSONDecodeError:
        history_list = []

    notes_list.append(
        {
            "note": note_text,
            "timestamp": ts,
        }
    )
    history_list.append(
        {
            "event": f"Note added: {note_text}",
            "timestamp": ts,
        }
    )

    cur.execute(
        """
        UPDATE applications
        SET notes = ?, history = ?
        WHERE id = ?
        """,
        (json.dumps(notes_list), json.dumps(history_list), app_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Note added successfully."})


if __name__ == "__main__":
    app.run(debug=True)
