from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta
import os
import json
import smtplib
from email.message import EmailMessage

import psycopg
from psycopg.rows import dict_row
from itsdangerous import URLSafeTimedSerializer
from werkzeug.utils import secure_filename

import base64



# =====
# Flask app setup
# =====
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "supersecretkey"

# Required so admin session survives on Render
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True
# Strengthen session persistence
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_PATH"] = "/"


serializer = URLSafeTimedSerializer(app.secret_key)


# Sessions expire after 30 minutes of inactivity    
app.permanent_session_lifetime = timedelta(minutes=30)

# Static uploads
app.config["UPLOAD_FOLDER"] = "static"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def is_admin(email):
    return email in {"chris@kraskickers.org"}


# =====
# Database helpers (Postgres via psycopg)
# =====
DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    """
    Open a new Postgres connection with rows returned as dicts.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return conn


def dictify_rows(rows):
    """
    Convert a sequence of row objects into a list of plain dictionaries.
    With dict_row this is mostly a no-op, but it keeps old code working.
    """
    result = []
    for r in rows:
        if isinstance(r, dict):
            result.append(dict(r))
        else:
            d = {}
            for k in r.keys():
                d[k] = r[k]
            result.append(d)
    return result





def current_user_email() -> str | None:
    """
    Return the currently verified email in the session, lowercased.
    """
    email = session.get("verified_email")
    if not email:
        return None
    return str(email).strip().lower()


def user_is_champion_for_opportunity(opportunity_id: int) -> bool:
    """
    Return True if the logged in user is a champion for the given opportunity.
    """
    email = current_user_email()
    if not email:
        return False

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM champions_opportunities co
                JOIN applications a ON co.champion_id = a.id
                WHERE co.opportunity_id = %s
                  AND LOWER(a.email) = %s
                LIMIT 1
                """,
                (opportunity_id, email),
            )
            row = cur.fetchone()
            return row is not None


def user_can_manage_opportunity(opportunity_id: int) -> bool:
    """
    Admins can manage every opportunity.
    Champions can manage only the opportunities they are assigned to.
    """
    if session.get("admin_verified"):
        return True
    return user_is_champion_for_opportunity(opportunity_id)


def get_opportunity_id_for_application(app_id: int) -> int | None:
    """
    Given an application id, find the related opportunity id by matching title.
    Returns None if no matching opportunity is found.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id
                FROM applications a
                LEFT JOIN opportunities o ON o.title = a.title
                WHERE a.id = %s
                """,
                (app_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            opp_id = row["id"]
            return opp_id


def require_admin():
    """
    Simple guard used at the top of admin-only routes.
    If admin is not verified, redirect to the menu.
    """
    if not session.get("admin_verified"):
        return redirect(url_for("menu"))
    return None


# =====
# Seed default opportunities IF the table is empty
# =====
def seed_opportunities():
    """
    Insert three sample opportunities only if the opportunities table
    contains zero rows. This is safe for Postgres and will not run
    on every request because it is called once on import.
    """
    try:
        conn = get_db_connection()
    except RuntimeError:
        # In case DATABASE_URL is not set during local tooling
        return

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM opportunities")
            row = cur.fetchone()
            count = row["cnt"] if row and "cnt" in row else (row[0] if row else 0)

            if count and count > 0:
                return

            sample_data = [
                (
                    "Social Media Ambassador",
                    "1-2 hours",
                    "3 months",
                    "Remote - Weekly",
                    "Help spread awareness about KRAS-targeted lung cancer via social media campaigns.",
                    "Basic social media skills. Training on key messages provided.",
                    "Remote",
                    "social_media.png",
                    json.dumps(
                        [
                            {"name": "Awareness", "color": "#2563eb"},
                            {"name": "Remote", "color": "#16a34a"},
                            {"name": "Flexible", "color": "#6b7280"},
                        ]
                    ),
                ),
                (
                    "Clinical Trial Navigator",
                    "2-4 hours",
                    "6 months",
                    "Remote - Monthly",
                    "Assist patients and families in understanding and navigating KRAS clinical trial options.",
                    "Background in healthcare or patient support preferred. Training provided.",
                    "Hybrid: Online and occasional in-person meetings.",
                    "clinical_navigator.png",
                    json.dumps(
                        [
                            {"name": "Clinical", "color": "#9333ea"},
                            {"name": "Patient Support", "color": "#16a34a"},
                            {"name": "Hybrid", "color": "#2563eb"},
                        ]
                    ),
                ),
                (
                    "Event Volunteer",
                    "4-8 hours",
                    "Per event",
                    "In-Person - At Event",
                    "Support KRAS Kickers awareness events with setup, check-in, and engagement.",
                    "Comfortable around crowds and public-facing roles.",
                    "Various event locations nationwide.",
                    "event_volunteer.png",
                    json.dumps(
                        [
                            {"name": "Events", "color": "#facc15"},
                            {"name": "In-Person", "color": "#dc2626"},
                        ]
                    ),
                ),
            ]

            for (
                title,
                time_txt,
                duration,
                mode,
                desc,
                reqs,
                location,
                image,
                tags_json,
            ) in sample_data:
                cur.execute(
                    """
                    INSERT INTO opportunities
                        (title, time, duration, mode, description,
                         requirements, location, image, tags, closed)
                    VALUES
                        (%s,   %s,   %s,       %s,   %s,
                         %s,           %s,       %s,    %s,   FALSE)
                    """,
                    (
                        title,
                        time_txt,
                        duration,
                        mode,
                        desc,
                        reqs,
                        location,
                        image,
                        tags_json,
                    ),
                )


# Call once at import time; if table already has data, it does nothing
try:
    seed_opportunities()
except Exception:
    # If something goes wrong here, the rest of the app should still run
    pass


# =====
# File upload helpers
# =====
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename: str) -> bool:
    if not filename:
        return False
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# =====
# Email + token helpers
# =====
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


# =====
# Core data helpers
# =====
def save_application(form_data: dict) -> int:
    """
    Insert a new volunteer application into Postgres.
    History and notes are stored as JSON text.
    """
    history_list = [
        {
            "event": "Application submitted",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    ]
    notes_list = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO applications
                    (first_name, last_name, email, phone, contact,
                     title, time, duration, mode, location,
                     comments, status, timestamp, history, notes)
                VALUES
                    (%s, %s, %s, %s, %s,
                     %s,   %s,   %s,      %s,   %s,
                     %s,      %s,      %s,        %s,      %s)
                RETURNING id
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
            row = cur.fetchone()
            app_id = row["id"] if isinstance(row, dict) else row[0]
            return int(app_id)
# =====
# Routes
# =====
@app.route("/logout")
def logout():
    session.clear()           # remove ALL session data
    session.modified = True   # force regeneration
    return redirect(url_for("index"))



@app.route("/activate/<token>")
def activate_email(token):
    email = confirm_activation_token(token)
    if not email:
        return "Activation link is invalid or expired", 400

    session["email_verified"] = True
    session["verified_email"] = email
    session.permanent = True

    return redirect(url_for("index", verified=1))


@app.route("/admin_request_access", methods=["POST"])
def admin_request_access():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()

    if not email.endswith("@kraskickers.org"):
        return {"error": "Admin access requires a @kraskickers.org email address."}, 400

    send_admin_activation_email(email)
    return {
        "message": "A verification link has been sent to your KRAS Kickers email."
    }


@app.route("/admin_activate/<token>")
def admin_activate(token):
    email = confirm_activation_token(token, max_age=3600)
    if not email or not email.endswith("@kraskickers.org"):
        return "Invalid or expired admin activation link.", 400

    session["admin_verified"] = True
    session["email_verified"] = True        # <--- REQUIRED
    session["verified_email"] = email       # <--- REQUIRED
    session.permanent = True
    session.modified = True


    return redirect(url_for("menu", admin_verified=1))


# =====
# Home page
# =====
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        form_email = (request.form.get("email") or "").strip().lower()
        verified_email = (session.get("verified_email") or "").strip().lower()

        if not session.get("email_verified"):
            return jsonify({
                "status": "error",
                "message": "Please verify your email before submitting the application."
            }), 400

        if form_email != verified_email:
            return jsonify({
                "status": "error",
                "message": "The email used in the application does not match the verified email."
            }), 400

        app_id = save_application(request.form.to_dict())
        return jsonify({
            "status": "success",
            "title": request.form.get("title"),
            "message": "Thank you. Your volunteer application has been submitted.",
            "application_id": app_id
        })

    verified_email = (session.get("verified_email") or "").strip().lower()

    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # Load all open opportunities
            cur.execute(
                "SELECT * FROM opportunities WHERE closed IS FALSE OR closed IS NULL"
            )
            rows = cur.fetchall()
            opportunities = dictify_rows(rows)

            # Load user's volunteer application history / assignments
            cur.execute(
                """
                SELECT id, title, timestamp, time, duration, mode, location, status
                FROM applications
                WHERE email = %s
                ORDER BY timestamp DESC
                """,
                (verified_email,),
            )
            my_assignments = dictify_rows(cur.fetchall())

            # Keep only Assigned or Pending
            my_assignments = [
                a for a in my_assignments 
                if a.get("status") in ("Assigned", "Pending")
            ]

            # Sort: Assigned first, Pending second
            status_order = {"Assigned": 0, "Pending": 1}
            my_assignments.sort(key=lambda a: status_order.get(a.get("status"), 2))

            # Determine champion or admin view
            if is_admin(verified_email):
                # Admin sees all opportunities as champion_opps
                champion_opps = opportunities.copy()
            else:
                # Normal champion-only filter
                cur.execute(
                    """
                    SELECT o.*
                    FROM champions_opportunities co
                    JOIN applications a ON co.champion_id = a.id
                    JOIN opportunities o ON co.opportunity_id = o.id
                    WHERE LOWER(a.email) = %s
                    ORDER BY o.id
                    """,
                    (verified_email,),
                )

                champion_opps = dictify_rows(cur.fetchall())


    # Normalize tags and frequency for ALL opportunities
    for opp in opportunities:
        tags_raw = opp.get("tags")
        if isinstance(tags_raw, str) and tags_raw.strip():
            try:
                opp["tags"] = json.loads(tags_raw)
            except json.JSONDecodeError:
                opp["tags"] = []
        elif tags_raw is None:
            opp["tags"] = []

        if "description" in opp and "desc" not in opp:
            opp["desc"] = opp["description"]

        opp["frequency"] = opp.get("mode", "")

    # Normalize tags for champion opportunities
    for opp in champion_opps:
        tags_raw = opp.get("tags")
        if isinstance(tags_raw, str) and tags_raw.strip():
            try:
                opp["tags"] = json.loads(tags_raw)
            except json.JSONDecodeError:
                opp["tags"] = []
        elif tags_raw is None:
            opp["tags"] = []

        if "description" in opp and "desc" not in opp:
            opp["desc"] = opp["description"]

        opp["frequency"] = opp.get("mode", "")

    return render_template(
        "index.html",
        opportunities=opportunities,
        my_assignments=my_assignments,
        champion_opps=champion_opps
    )

# =====
# Admin menu
# =====
@app.route("/menu")
def menu():
    if session.get("admin_verified"):
        # Fully restore admin session
        session["email_verified"] = True
        session["verified_email"] = session.get("verified_email", "admin@kraskickers.org")
        session["admin_verified"] = True

        session.permanent = True
        session.modified = True

    return render_template("Menu.html")



# =====
# Manage active opportunities
# =====
@app.route("/manage", methods=["GET"])
def manage():
    session.permanent = True
    auth = require_admin()
    if auth:
        return auth

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Load open opportunities
            cur.execute(
                "SELECT * FROM opportunities WHERE closed IS FALSE OR closed IS NULL"
            )
            rows = cur.fetchall()

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

        if "description" in opp and "desc" not in opp:
            opp["desc"] = opp["description"]

        opp["frequency"] = opp.get("mode", "")

    # ================================
    # NEW CODE: Load Champion-Leader candidates
    # ================================

    champion_candidates = []

    # 1. Find the opportunity_id for Champion-Leader
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id
                FROM opportunities
                WHERE LOWER(title) = LOWER(%s)
                  AND (closed IS FALSE OR closed IS NULL)
                LIMIT 1
            """, ("Champion-Leader",))
            row = cur.fetchone()
            champion_leader_opp_id = row["id"] if row else None

    # 2. Load all volunteers whose Champion-Leader applications are Assigned
    if champion_leader_opp_id:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, first_name, last_name, email
                    FROM applications
                    WHERE status = 'Assigned'
                        AND LOWER(TRIM(title)) = LOWER(TRIM('Champion-Leader'))
                    ORDER BY first_name, last_name
                """)

                rows = cur.fetchall()

                for r in rows:
                    champion_candidates.append({
                        "id": r["id"],
                        "name": f"{r['first_name']} {r['last_name']}",
                        "email": r["email"]
                    })

    # ================================

    return render_template(
        "manage.html",
        opportunities=opportunities,
        champion_candidates=champion_candidates
    )


# =====
# Champion APIs
# =====
@app.route("/api/champions")
def get_champions():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, first_name, last_name, email
                FROM applications
                WHERE is_champion IS TRUE
                ORDER BY first_name, last_name
                """
            )
            rows = cur.fetchall()

    champions = dictify_rows(rows)
    return jsonify(champions)


@app.route("/api/opportunity_champions/<int:opp_id>")
def get_opportunity_champions(opp_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.first_name,
                    a.last_name,
                    a.email
                FROM champions_opportunities co
                JOIN applications a ON co.champion_id = a.id
                WHERE co.opportunity_id = %s
                ORDER BY a.first_name, a.last_name
                """,
                (opp_id,),
            )
            rows = cur.fetchall()

    champions = dictify_rows(rows)
    return jsonify(champions)


@app.route("/api/assign_champion", methods=["POST"])
def assign_champion():
    if not session.get("admin_verified"):
        return jsonify({"error": "Not authorized"}), 403

    champion_id = request.form.get("champion_id")
    opportunity_id = request.form.get("opportunity_id")

    if not champion_id or not opportunity_id:
        return jsonify({"error": "Missing data"}), 400

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM champions_opportunities
                WHERE champion_id = %s AND opportunity_id = %s
                """,
                (champion_id, opportunity_id),
            )
            existing = cur.fetchone()

            if existing:
                return jsonify({"message": "Champion already assigned."})

            cur.execute(
                """
                INSERT INTO champions_opportunities (champion_id, opportunity_id)
                VALUES (%s, %s)
                """,
                (champion_id, opportunity_id),
            )

    return jsonify({"message": "Champion assigned successfully."})


# =====
# Add opportunity
# =====
@app.route("/add", methods=["POST"])
def add_opportunity():
    auth = require_admin()
    if auth:
        return auth

    image_base64 = None
    if "image" in request.files:
        file = request.files["image"]
        if file and allowed_file(file.filename):
            encoded = base64.b64encode(file.read()).decode("utf-8")
            image_base64 = encoded


    tags_json = request.form.get("tags_json") or request.form.get("tags") or "[]"
    try:
        tags = json.loads(tags_json)
    except Exception:   
        tags = []
    tags_json = json.dumps(tags)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO opportunities
                (title, time, duration, mode, description, requirements, location, image_base64, tags, closed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
                """,
                (
                    request.form.get("title"),
                    request.form.get("time", ""),
                    request.form.get("duration", ""),
                    request.form.get("mode", ""),
                    request.form.get("desc", ""),
                    request.form.get("requirements", ""),
                    request.form.get("location", ""),
                    image_base64,
                    tags_json,
                ),
            )

    return jsonify({"message": "Opportunity added."})


# =====
# Update opportunity
# =====
@app.route("/update/<int:opp_id>", methods=["POST"])
def update_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth

    tags_json = request.form.get("tags_json") or request.form.get("tags") or "[]"
    try:
        tags = json.loads(tags_json)
    except Exception:
        tags = []
    tags_json = json.dumps(tags)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE opportunities
                SET title = %s,
                    time = %s,
                    duration = %s,
                    mode = %s,
                    description = %s,
                    requirements = %s,
                    location = %s,
                    tags = %s
                WHERE id = %s
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

            import base64   # ← ensure this is at the top of app.py

            # inside update_opportunity() – replace your whole image block with this:
            if "image" in request.files:
                file = request.files["image"]
                if file and allowed_file(file.filename):
                    encoded = base64.b64encode(file.read()).decode("utf-8")
                    cur.execute(
                        "UPDATE opportunities SET image_base64 = %s WHERE id = %s",
                        (encoded, opp_id),
                    )



    return jsonify({"message": "Opportunity updated."}) 


# =====
# Delete opportunity
# =====
@app.route("/delete/<int:opp_id>", methods=["POST"])
def delete_opportunity(opp_id):
    return close_opportunity(opp_id)

    return jsonify({"message": "Opportunity closed."})



# =====
# Close / reopen opportunity
# =====
@app.route("/close_opportunity/<int:opp_id>", methods=["POST"])
def close_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth

    closed_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # 1. Mark the opportunity as closed
            cur.execute("""
                UPDATE opportunities
                SET closed = TRUE, closed_date = %s
                WHERE id = %s
            """, (closed_date, opp_id))

            # 2. Close volunteer applications tied to this opportunity
            cur.execute("""
                UPDATE applications
                SET status = 'Closed-Completed'
                WHERE LOWER(TRIM(title)) = LOWER(
                    TRIM((SELECT title FROM opportunities WHERE id = %s))
                )
                AND status IN ('Assigned', 'Pending')
            """, (opp_id,))

            # 3. Remove all champions from this opportunity
            cur.execute("""
                DELETE FROM champions_opportunities
                WHERE opportunity_id = %s
            """, (opp_id,))

        conn.commit()

    return jsonify({
        "message": "Opportunity closed. All assigned volunteers have been closed out and all champions removed."
    })


@app.route("/api/remove_champion", methods=["POST"])
def remove_champion():
    if not session.get("admin_verified"):
        return jsonify({"error": "Not authorized"}), 403

    champion_id = request.form.get("champion_id")
    opportunity_id = request.form.get("opportunity_id")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM champions_opportunities
                WHERE champion_id = %s AND opportunity_id = %s
            """, (champion_id, opportunity_id))

    return jsonify({"message": "Champion removed."})

@app.route("/api/opportunity/<int:opp_id>", methods=["GET"])
def api_get_opportunity(opp_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, time, duration, mode, location,
                       requirements, desc, tags, image_base64
                FROM opportunities
                WHERE id = %s
            """, (opp_id,))
            row = cur.fetchone()

            if not row:
                return jsonify({"error": "Opportunity not found"}), 404

            # Parse tags if stored as JSON string
            tags = []
            if row[8]:
                try:
                    parsed = json.loads(row[8])
                    if isinstance(parsed, list):
                        tags = parsed
                except Exception:
                    tags = []

            return jsonify({
                "id": row[0],
                "title": row[1],
                "time": row[2],
                "duration": row[3],
                "mode": row[4],
                "location": row[5],
                "requirements": row[6],
                "desc": row[7],
                "tags": tags,
                "image_base64": row[9]
            })


@app.route("/reopen_opportunity/<int:opp_id>", methods=["POST"])
def reopen_opportunity(opp_id):
    auth = require_admin()
    if auth:
        return auth

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE opportunities
                SET closed = FALSE, closed_date = NULL
                WHERE id = %s
                """,
                (opp_id,),
            )

    return jsonify({"message": "Opportunity reopened."})


# =====
# Closed opportunities
# =====
@app.route("/closed")
def closed_opportunities():
    session.permanent = True
    auth = require_admin()
    if auth:
        return auth

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM opportunities WHERE closed IS TRUE")
            opp_rows = cur.fetchall()

            cur.execute("SELECT * FROM applications")
            apps_rows = cur.fetchall()

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

        if "description" in opp and "desc" not in opp:
            opp["desc"] = opp["description"]

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


# =====
# View applicants for a given opportunity
# =====
@app.route("/applicants/<int:opp_id>")
def view_applicants(opp_id):
    """
    View applicants for an opportunity.

    Admins:
        can open for any opportunity
        see admin view

    Champions:
        can open only opportunities they are assigned to
        share the same screen, but template can hide admin-only controls
    """
    # Permission check: admin or champion for this opportunity
    # Admins can view ALL opportunities
    if session.get("admin_verified"):
        pass  # allow admin

    # Champions must be assigned to the opportunity
    elif not user_is_champion_for_opportunity(opp_id):
        return redirect(url_for("index"))


    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, time, duration, mode, description, requirements, "
                "location, image_base64, tags, closed, closed_date "
                "FROM opportunities WHERE id = %s",
                (opp_id,),
            )
            row = cur.fetchone()

            if not row:
                return "Opportunity not found", 404

            # Convert opportunity row to dict correctly
            opportunity = dict(row)
            if "description" in opportunity:
                opportunity["desc"] = opportunity["description"]

            # Normalize tags
            tags_raw = opportunity.get("tags")
            if isinstance(tags_raw, str) and tags_raw.strip():
                try:
                    opportunity["tags"] = json.loads(tags_raw)
                except json.JSONDecodeError:
                    opportunity["tags"] = []
            elif tags_raw is None:
                opportunity["tags"] = []
            opportunity["frequency"] = opportunity.get("mode", "")


            # Fetch applicants using the same logic you tested in DBeaver:
            # match applications whose title matches this opportunity's title,
            # case-insensitive and trimmed
            cur.execute(
                """
                SELECT
                    id, first_name, last_name, email, phone, contact,
                    title, time, duration, mode, location,
                    comments, status, timestamp, history, notes
                FROM applications
                WHERE LOWER(TRIM(title)) = LOWER(
                    TRIM(
                        (SELECT title FROM opportunities WHERE id = %s)
                    )
                )
                ORDER BY timestamp DESC
                """,
                (opp_id,),
            )
            rows = cur.fetchall()

    applicants = []
    for r in rows:
        app_entry = dict(r)

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

        applicants.append(app_entry)

    # Back button behavior:
    # Admins go back to the admin menu
    # Champions go back to the main volunteer page
    # Admins go back to manage page
    # Champions / volunteers go back to volunteer dashboard
    if session.get("admin_verified"):
        back_to_menu_url = url_for("manage")
    else:
        back_to_menu_url = url_for("index", verified=1)

    is_champion_view = not session.get("admin_verified")


    return render_template(
        "applicants.html",
        opportunity=opportunity,
        applicants=applicants,
        back_to_menu_url=back_to_menu_url,
        champion_mode=is_champion_view,
    )


# =====
# Check volunteer status
# =====
@app.route("/check")
def check_volunteer():
    email = (request.args.get("email") or "").strip().lower()
    session.permanent = True


    if not email:
        return jsonify({"error": "Email is required"}), 400

    response = {
        "exists": False,
        "first_name": "",
        "last_name": "",
        "email": email,
        "phone": "",
        "assignments": [],
        "activation_message": "",
        "champion_assignments": [],
    }

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM applications
                WHERE LOWER(email) = %s
                ORDER BY timestamp DESC
                """,
                (email,),
            )
            rows = cur.fetchall()

            if rows:
                latest = rows[0]
                response["exists"] = True
                response["first_name"] = latest.get("first_name") or ""
                response["last_name"] = latest.get("last_name") or ""
                response["email"] = latest.get("email") or ""
                response["phone"] = latest.get("phone") or ""

                session_email = (session.get("verified_email") or "").strip().lower()
                session_verified = session.get("email_verified", False)

                if session_verified and session_email == email:
                    response["activation_message"] = ""
                    response["redirect"] = "/?verified=1"
                else:
                    send_activation_email(email)
                    response[
                        "activation_message"
                    ] = "We just sent a verification email. Please click the link in that email so you can submit your application."
#add Assigned
                if response["exists"] and response.get("activation_message", "") == "":
                    cur.execute(
                        """
                        SELECT
                            a.timestamp AS submitted_at,
                            a.title,
                            a.status,
                            o.time        AS time_commitment,
                            o.duration    AS duration,
                            o.mode        AS frequency,
                            o.location    AS location
                        FROM applications a
                        LEFT JOIN opportunities o
                            ON a.title = o.title
                        WHERE
                            LOWER(a.email) = %s
                           AND a.status IN ('Assigned', 'Pending')
                        ORDER BY a.timestamp DESC
                        """,
                        (email,),
                    )
                    assignment_rows = cur.fetchall()
                    assignments = []
                    for row in assignment_rows:
                        assignments.append(
                            {
                                "submitted_at": row.get("submitted_at"),
                                "title": row.get("title"),
                                "status": row.get("status"), 
                                "time_commitment": row.get("time_commitment"),
                                "duration": row.get("duration"),
                                "frequency": row.get("frequency"),
                                "location": row.get("location"),
                            }
                        )
                    response["assignments"] = assignments
            else:
                send_activation_email(email)
                response[
                    "activation_message"
                ] = "We just sent a verification email. Please click the link in that email so you can submit your application."
    # Load champion assignments for this email
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id AS opp_id, o.title
                FROM champions_opportunities co
                JOIN applications a ON co.champion_id = a.id
                JOIN opportunities o ON co.opportunity_id = o.id
                WHERE LOWER(a.email) = %s
                ORDER BY o.title
                """,
                (email,),
            )
            rows = cur.fetchall()

    champions = []
    for r in rows:
        champions.append({"opp_id": r.get("opp_id"), "title": r.get("title")})

    response["champion_assignments"] = champions

    return jsonify(response)


# =====
# Review all applications
# =====
@app.route("/review")
def review():
    session.permanent = True
    auth = require_admin()
    if auth:
        return auth

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM applications ORDER BY timestamp DESC")
            rows = cur.fetchall()

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
    session.permanent = True
    """
    Update the status of an application.

    Admins:
        can update any application

    Champions:
        can update only applications for opportunities they champion
    """
    # Prefer explicit opp_id from the front end, fall back to lookup by title
    opp_id = request.args.get("opp_id", type=int)
    if opp_id is None:
        opp_id = get_opportunity_id_for_application(app_id)

    # Permission check
    can_manage = False
    if session.get("admin_verified"):
        can_manage = True
    elif opp_id is not None and user_is_champion_for_opportunity(opp_id):
        can_manage = True

    if not can_manage:
        return jsonify({"error": "Not authorized"}), 403

    new_status = request.form.get("status", "Pending")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    allowed_statuses = {
        "Pending",
        "Assigned",
        "Closed-Completed",
        "Closed-Not Assigned"
    }

    if new_status not in allowed_statuses:
        new_status = "Pending"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT history FROM applications WHERE id = %s",
                (app_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Application not found"}), 404

            # FIX: RealDictCursor returns dict, not tuple
            history_raw = row.get("history") or "[]"

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
                SET status = %s, history = %s
                WHERE id = %s
                """,
                (new_status, json.dumps(history_list), app_id),
            )
            # ==========================================
            # AUTO-PROMOTE TO CHAMPION IF ASSIGNED
            # ==========================================
            cur.execute(
                "SELECT title FROM applications WHERE id = %s",
                (app_id,)
            )
            row2 = cur.fetchone()

            if row2 and row2.get("title", "").strip().lower() == "champion-leader":
                if new_status == "Assigned":
                    cur.execute(
                        "UPDATE applications SET is_champion = TRUE WHERE id = %s",
                        (app_id,)
                    )
            conn.commit()

    return jsonify({"message": "Status updated successfully"})


@app.route("/delete_application/<int:app_id>", methods=["POST"])
def delete_application(app_id):
    session.permanent = True
    auth = require_admin()
    if auth:
        return auth

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM applications WHERE id = %s", (app_id,))

    return jsonify({"message": "Application deleted successfully."})


# =====
# Volunteers overview
# =====
@app.route("/volunteers")
def volunteers():
    session.permanent = True
    auth = require_admin()
    if auth:
        return auth

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM applications ORDER BY timestamp DESC")
            rows = cur.fetchall()

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


# =====
# Volunteer detail
# =====
@app.route("/volunteer/<int:app_id>")
def volunteer_detail(app_id):
    session.permanent = True
    """
    Volunteer detail and assignment screen.

    Admins:
        can open for any application
    Champions:
        can open only if they are champion for the related opportunity
        cannot delete applications (delete route still admin-only)
    """
    # Determine the opportunity id related to this application
    opp_id = get_opportunity_id_for_application(app_id)

    # Permission check
    can_manage = False
    if session.get("admin_verified"):
        can_manage = True
    elif opp_id is not None and user_is_champion_for_opportunity(opp_id):
        can_manage = True

    if not can_manage:
        can_manage = False

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, first_name, last_name, email, phone, contact,
                       title, time, duration, mode, location,
                       comments, status, timestamp, history, notes
                FROM applications
                WHERE id = %s
                """,
                (app_id,),
            )
            row = cur.fetchone()

            if not row:
                return "Application not found", 404

            cols = [
                "id",
                "first_name",
                "last_name",
                "email",
                "phone",
                "contact",
                "title",
                "time",
                "duration",
                "mode",
                "location",
                "comments",
                "status",
                "timestamp",
                "history",
                "notes",
            ]
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

            # Try to look up the opportunity id again by title, in case it was missing
            if opp_id is None:
                cur.execute(
                    "SELECT id FROM opportunities WHERE title = %s",
                    (app_entry.get("title", ""),),
                )
                row2 = cur.fetchone()
                if row2:
                    opp_id = row2["id"]


    back_opp_id = opp_id
    is_champion_view = not session.get("admin_verified")
    allow_delete = bool(session.get("admin_verified"))

    return render_template(
        "review_detail.html",
        app=app_entry,
        back_opp_id=back_opp_id,
        champion_mode=is_champion_view,
        allow_delete=allow_delete,
    )


@app.route("/api/applicant/<int:app_id>")
def api_get_applicant(app_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, first_name, last_name, email, phone, contact,
                       title, time, duration, mode, location,
                       comments, status, timestamp, history, notes
                FROM applications
                WHERE id = %s
            """, (app_id,))
            row = cur.fetchone()

    if not row:
        return jsonify({"error": "Applicant not found"}), 404

    cols = [
        "id", "first_name", "last_name", "email", "phone", "contact",
        "title", "time", "duration", "mode", "location",
        "comments", "status", "timestamp", "history", "notes"
    ]
    data = dict(zip(cols, row))

    return jsonify(data)

@app.route("/api/applicant/<int:app_id>/update", methods=["POST"])
def api_update_applicant(app_id):
    new_status = request.form.get("status")
    new_note = request.form.get("note")

    if not new_status:
        return jsonify({"error": "Missing status"}), 400

    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # Save status
            cur.execute("""
                UPDATE applications
                SET status = %s
                WHERE id = %s
            """, (new_status, app_id))

            # Append note (if provided)
            if new_note and new_note.strip():
                cur.execute("""
                    UPDATE applications
                    SET notes = COALESCE(notes, '') || %s
                    WHERE id = %s
                """, ("\n" + new_note.strip(), app_id))

        conn.commit()

    return jsonify({"success": True})


@app.route("/view_applications/<int:opp_id>")
def view_applications(opp_id):
    """
    Loads the unified View Applications page.
    Shows:
      Opportunity info
      All applicants for that opportunity
      Lets the JS panel load applicant details dynamically
    """
    # AUTH: Admins can view any opportunity
    if not session.get("admin_verified"):
        # Champions must be assigned
        if not user_is_champion_for_opportunity(opp_id):
            return redirect(url_for("index"))

    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # Load opportunity
            cur.execute("""
                SELECT id, title, time, duration, mode, description,
                       requirements, location, image_base64, tags, closed, closed_date
                FROM opportunities
                WHERE id = %s
            """, (opp_id,))
            row = cur.fetchone()

            if not row:
                return "Opportunity not found", 404

            opportunity = dict(row)
            if "description" in opportunity:
                opportunity["desc"] = opportunity["description"]

            # Parse tags JSON
            tags_raw = opportunity.get("tags")
            try:
                if tags_raw:
                    opportunity["tags"] = json.loads(tags_raw)
                else:
                    opportunity["tags"] = []
            except:
                opportunity["tags"] = []

            # Load applicants
            cur.execute("""
                SELECT id, first_name, last_name, email, phone, contact,
                       title, time, duration, mode, location,
                       comments, status, timestamp, history, notes
                FROM applications
                WHERE LOWER(TRIM(title)) = LOWER(
                    TRIM((SELECT title FROM opportunities WHERE id = %s))
                )
                ORDER BY timestamp DESC
            """, (opp_id,))
            raw_rows = cur.fetchall()

    applicants = []
    for r in raw_rows:
        a = dict(r)

        # Parse history JSON
        history_raw = a.get("history") or "[]"
        try:
            a["history"] = json.loads(history_raw)
        except:
            a["history"] = []

        # Parse notes JSON
        notes_raw = a.get("notes") or "[]"
        try:
            a["notes"] = json.loads(notes_raw)
        except:
            a["notes"] = []

        applicants.append(a)

    # Back button routing: Admins → manage, Champions → index
    session.permanent = True  # <-- REQUIRED FIX
    back_to_menu_url = (
        url_for("manage") if session.get("admin_verified") else url_for("index", verified=1)
    )



    return render_template(
        "view_applications.html",
        opportunity=opportunity,
        applicants=applicants,
        back_to_menu_url=back_to_menu_url
    )

# =====
# Admin notes
# =====
@app.route("/add_note/<int:app_id>", methods=["POST"])
def add_note(app_id):
    session.permanent = True
    """
    Add an admin or champion note to an application.

    Admins:
        can add notes for any application

    Champions:
        can add notes only for applications for opportunities they champion
    """
    note_text = (request.form.get("note") or "").strip()
    if not note_text:
        return jsonify({"error": "Note cannot be empty."}), 400

    # Prefer explicit opp_id from the front end, fall back to lookup
    opp_id = request.args.get("opp_id", type=int)
    if opp_id is None:
        opp_id = get_opportunity_id_for_application(app_id)

    # Permission check
    can_manage = False
    if session.get("admin_verified"):
        can_manage = True
    elif opp_id is not None and user_is_champion_for_opportunity(opp_id):
        can_manage = True

    if not can_manage:
        return jsonify({"error": "Not authorized"}), 403

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT history, notes FROM applications WHERE id = %s",
                (app_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Application not found"}), 404

            # FIX: RealDictCursor returns dict keys, not tuple indices
            history_raw = row.get("history") or "[]"
            notes_raw = row.get("notes") or "[]"

            try:
                history_list = json.loads(history_raw)
            except json.JSONDecodeError:
                history_list = []

            try:
                notes_list = json.loads(notes_raw)
            except json.JSONDecodeError:
                notes_list = []

            note_entry = {
                "note": note_text,
                "timestamp": ts,
            }
            notes_list.append(note_entry)

            history_list.append(
                {
                    "event": f"Note added: {note_text}",
                    "timestamp": ts,
                }
            )

            cur.execute(
                """
                UPDATE applications
                SET notes = %s, history = %s
                WHERE id = %s
                """,
                (json.dumps(notes_list), json.dumps(history_list), app_id),
            )
            conn.commit()

    return jsonify({"message": "Note added successfully"})





# =====
# Local dev entrypoint
# =====
if __name__ == "__main__":
    app.run(debug=True)
