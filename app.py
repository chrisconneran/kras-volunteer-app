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
# Ensure uploads folder works on Render
app.config["UPLOAD_FOLDER"] = "static"

# Create the folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


from datetime import timedelta
app.permanent_session_lifetime = timedelta(minutes=30)



def require_admin():
    if not session.get("admin_verified"):
        return redirect(url_for("menu"))


import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    conn = psycopg.connect(DATABASE_URL)
    return conn




def seed_opportunities():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS cnt FROM opportunities")
    count = cur.fetchone()["cnt"]
    if count == 0:
        sample_data = [
            (
                "Social Media Ambassador",
                "2-3 hrs/week",
                "3 months",
                "Remote",
                "Help spread awareness about KRAS-targeted lung cancer via social media campaigns.",
                "Basic social media skills. Training on key messages provided.",
                "Remote",
                "social_media.png",
                json.dumps(["Awareness", "Remote", "Flexible"]),
            ),
            (
                "Clinical Trial Navigator",
                "4-5 hrs/week",
                "6 months",
                "Hybrid",
                "Assist patients and families in understanding and navigating KRAS clinical trial options.",
                "Background in healthcare or patient support preferred. Training provided.",
                "Hybrid: Online and occasional in-person meetings.",
                "clinical_navigator.png",
                json.dumps(["Clinical", "Patient Support", "Hybrid"]),
            ),
            (
                "Event Volunteer",
                "4-6 hrs/event",
                "Per event",
                "In-Person",
                "Support KRAS Kickers awareness events with setup, check-in, and engagement.",
                "Comfortable around crowds and public-facing roles.",
                "Various event locations nationwide.",
                "event_volunteer.png",
                json.dumps(["Events", "In-Person"]),
            ),
        ]

        for title, time_txt, duration, mode, desc, reqs, location, image, tags in sample_data:
            cur.execute(
                """
                INSERT INTO opportunities
                (title, time, duration, mode, description, requirements, location, image, tags, closed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (title, time_txt, duration, mode, desc, reqs, location, image, tags),
            )

        conn.commit()
    conn.close()



seed_opportunities()


def dictify_rows(rows):
    result = []
    for r in rows:
        d = {}
        for k in r.keys():
            d[k] = r[k]
        result.append(d)
    return result


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename: str) -> bool:
    if not filename:
        return False
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def save_application(form_data: dict) -> int:
    history_list = [
        {
            "event": "Application submitted",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    ]
    notes_list = []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO applications
        (first_name, last_name, email, phone, contact, title, time, duration, mode, location, comments, status, timestamp, history, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            form_data.get("mode"),
            form_data.get("location"),
            form_data.get("comments"),
            "Pending",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            json.dumps(history_list),
            json.dumps(notes_list),
        ),
    )
    conn.commit()
    app_id = cur.lastrowid
    conn.close()
    return app_id


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

    text_body = f"""Thank you for your interest in volunteering with KRAS Kickers.

To continue with your volunteer application, confirm your email by clicking this link:

{activation_link}

If you did not request this, you can ignore this message.
"""

    html_body = f"""
    <html>
      <body>
        <p>Thank you for your interest in volunteering with KRAS Kickers.</p>
        <p>To continue with your volunteer application, confirm your email by clicking the link below:</p>
        <p><a href="{activation_link}" target="_self">Click here to verify your email</a></p>
        <p>If you did not request this, you can ignore this message.</p>
      </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "no-reply@kraskickers.org")
    msg["To"] = recipient_email

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_user and smtp_password:
            server.starttls()
            server.login(smtp_user, smtp_password)
        server.send_message(msg)

@app.route("/logout")
def logout():
    session.pop("email_verified", None)
    session.pop("verified_email", None)
    return redirect(url_for("index"))


def send_admin_activation_email(recipient_email: str) -> None:
    token = generate_activation_token(recipient_email)
    activation_link = url_for("admin_activate", token=token, _external=True)

    subject = "KRAS Kickers Admin Access Verification"
    body = f"""An admin access request was received for this KRAS Kickers email.

To continue to the admin dashboard, confirm your email by clicking this link:

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

    # Redirect user directly to main page like Google/Amazon
    return redirect(url_for("index", verified=1))


# --- HOME PAGE ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        form_email = request.form.get("email", "").strip().lower()
        verified_email = session.get("verified_email", "").strip().lower()

        if not session.get("email_verified"):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Please verify your email before submitting the application.",
                    }
                ),
                400,
            )

        if form_email != verified_email:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "The email used in the application does not match the verified email.",
                    }
                ),
                400,
            )

        app_id = save_application(request.form.to_dict())
        return jsonify(
    {
        "status": "success",
        "title": request.form.get("title"),
        "message": "Thank you! Your volunteer application has been submitted.",
        "application_id": app_id,
    }
)


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

@app.route("/api/champions")
def get_champions():
    conn = get_db_connection()
    champions = conn.execute(
        "SELECT id, first_name, last_name, email FROM applications WHERE is_champion = 1 ORDER BY first_name"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in champions])

@app.route("/assign_champion", methods=["POST"])
def assign_champion():
    if not session.get("admin_verified"):
        return jsonify({"error": "Not authorized"}), 403

    data = request.json
    champion_id = data.get("champion_id")
    opportunity_id = data.get("opportunity_id")

    if not champion_id or not opportunity_id:
        return jsonify({"error": "Missing data"}), 400

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO champions_opportunities (champion_id, opportunity_id) VALUES (?, ?)",
        (champion_id, opportunity_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Champion assigned successfully"})

@app.route("/api/opportunity_champions/<int:opp_id>")
def get_opportunity_champions(opp_id):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.id, a.first_name, a.last_name, a.email
        FROM champions_opportunities c
        JOIN applications a ON c.champion_id = a.id
        WHERE c.opportunity_id = ?
        """,
        (opp_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])



# --- Add Opportunity ---
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
        (title, time, duration, mode, desc, requirements, location, image, tags, closed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            request.form.get("title"),
            request.form.get("time", ""),
            request.form.get("duration", ""),
            request.form.get("mode", ""),
            request.form.get("description", ""),
            request.form.get("requirements", ""),
            request.form.get("location", ""),
            image_path if image_path else "default.png",
            tags_json,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity added!"})


@app.route("/admin_request_access", methods=["POST"])
def admin_request_access():
    data = request.get_json()
    email = data.get("email", "").strip().lower()

    if not email.endswith("@kraskickers.org"):
        return {"error": "Admin access requires a @kraskickers.org email address."}, 400

    send_admin_activation_email(email)
    return {"message": "A verification link has been sent to your KRAS Kickers email."}


@app.route("/admin_activate/<token>")
def admin_activate(token):
    email = confirm_activation_token(token, max_age=3600)
    if not email or not email.endswith("@kraskickers.org"):
        return "Invalid or expired admin activation link.", 400

    # Mark admin as verified
    session["admin_verified"] = True
    session.permanent = True

    # Redirect directly back to the menu
    return redirect(url_for("menu", admin_verified=1))



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

    update_fields = (
        request.form.get("title"),
        request.form.get("time", ""),
        request.form.get("duration", ""),
        request.form.get("mode", ""),
        request.form.get("description", ""),
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
    return jsonify({"message": "Opportunity marked as closed."})


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
    return jsonify({"message": "Opportunity reopened."})


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

    return render_template(
        "closed.html",
        opportunities=opportunities,
        applications=applications,
    )


# --- View Applicants ---
@app.route("/applicants/<int:opp_id>")
def view_applicants(opp_id):
    auth = require_admin()
    if auth:
        return auth

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
    opportunity["frequency"] = opportunity.get("mode", "")

    applicants = dictify_rows(applicants_rows)
    for app_entry in applicants:
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

    return render_template(
        "applicants.html",
        opportunity=opportunity,
        applicants=applicants,
    )


# --- Check Volunteer Status ---
@app.route("/check")
def check_volunteer():
    email = request.args.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM applications WHERE LOWER(email) = ? ORDER BY timestamp DESC",
        (email,),
    )
    rows = cur.fetchall()

    response = {
        "exists": False,
        "first_name": "",
        "last_name": "",
        "email": email,
        "phone": "",
        "assignments": [],
        "activation_message": "",
    }

    if rows:
        latest = rows[0]
        response["exists"] = True
        response["first_name"] = latest["first_name"]
        response["last_name"] = latest["last_name"]
        response["email"] = latest["email"]
        response["phone"] = latest["phone"] or ""

        session_email = session.get("verified_email", "").strip().lower()
        session_verified = session.get("email_verified", False)

        if session_verified and session_email == email:
            response["activation_message"] = ""
            response["redirect"] = "/?verified=1"

        else:
            send_activation_email(email)
            response[
                "activation_message"
            ] = "We just sent a verification email. Please click the link in that email so you can submit your application."

        if response["exists"] and response["activation_message"] == "":
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
            response["assignments"] = assignments

    else:
        send_activation_email(email)
        response[
            "activation_message"
        ] = "We just sent a verification email. Please click the link in that email so you can submit your application."

    conn.close()
    return jsonify(response)


# --- Review ---
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


@app.route("/update_status/<int:app_id>", methods=["POST"])
def update_status(app_id):
    auth = require_admin()
    if auth:
        return auth

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
    auth = require_admin()
    if auth:
        return auth

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Application deleted successfully."})




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


# --- Volunteer Detail ---
@app.route("/volunteer/<int:app_id>")
def volunteer_detail(app_id):
    auth = require_admin()
    if auth:
        return auth

    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?",
        (app_id,),
    ).fetchone()

    if not row:
        conn.close()
        return "Application not found", 404

    app_entry = dict(row)
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

    opp_row = conn.execute(
        "SELECT id FROM opportunities WHERE title = ?",
        (app_entry.get("title", ""),),
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
    auth = require_admin()
    if auth:
        return auth

    note_text = request.form.get("note", "").strip()
    if not note_text:
        return jsonify({"error": "Note cannot be empty."}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT history, notes FROM applications WHERE id = ?",
        (app_id,),
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Application not found"}), 404

    history_raw = row["history"] or "[]"
    try:
        history_list = json.loads(history_raw)
    except json.JSONDecodeError:
        history_list = []

    notes_raw = row["notes"] or "[]"
    try:
        notes_list = json.loads(notes_raw)
    except json.JSONDecodeError:
        notes_list = []

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    note_entry = {
        "note": note_text,
        "timestamp": ts,
    }
    notes_list.append(note_entry)

    history_list.append(
        {
            "event": "Admin note added",
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
@app.route("/api/champions")
def api_champions():
    conn = get_db()
    c = conn.cursor()

    # Fetch volunteers who applied to the "Champion" opportunity AND were approved
    c.execute("""
        SELECT id, first_name, last_name, email
        FROM volunteers
        WHERE applied_for = 'Champion'
        AND status = 'Approved'
    """)

    rows = c.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])

@app.route("/api/opportunity_champions/<int:opp_id>")
def api_opportunity_champions(opp_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT v.id, v.first_name, v.last_name, v.email
        FROM champions_opportunities co
        JOIN volunteers v ON co.champion_id = v.id
        WHERE co.opportunity_id = ?
    """, (opp_id,))

    rows = c.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])
@app.route("/api/assign_champion", methods=["POST"])
def api_assign_champion():
    champion_id = request.form.get("champion_id")
    opportunity_id = request.form.get("opportunity_id")

    if not champion_id or not opportunity_id:
        return jsonify({"error": "Missing data"}), 400

    conn = get_db()
    c = conn.cursor()

    # Prevent duplicate assignments
    c.execute("""
        SELECT id FROM champions_opportunities
        WHERE champion_id = ? AND opportunity_id = ?
    """, (champion_id, opportunity_id))

    if c.fetchone():
        conn.close()
        return jsonify({"message": "Champion already assigned."})

    c.execute("""
        INSERT INTO champions_opportunities (champion_id, opportunity_id)
        VALUES (?, ?)
    """, (champion_id, opportunity_id))

    conn.commit()
    conn.close()

    return jsonify({"message": "Champion assigned successfully."})


if __name__ == "__main__":
    app.run(debug=True)
