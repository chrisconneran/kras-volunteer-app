from flask import Flask, render_template, request, jsonify
from datetime import datetime
import json, os, sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "supersecretkey"

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

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def dictify_rows(rows):
    return [dict(row) for row in rows]


# --- Shared POST handler for volunteer applications ---
def _handle_application_post():
    form_data = request.form.to_dict()
    form_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    form_data["status"] = "Pending"
    form_data["history"] = json.dumps([{
        "event": "Application submitted",
        "timestamp": form_data["timestamp"]
    }])
    form_data["notes"] = json.dumps([])

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications 
        (first_name, last_name, email, phone, contact, title, time, duration, location, comments, status, timestamp, history, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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
        form_data["status"],
        form_data["timestamp"],
        form_data["history"],
        form_data["notes"]
    ))
    conn.commit()
    conn.close()

    return jsonify({
        "message": "Application submitted successfully!",
        "title": form_data.get("title", "Volunteer Opportunity")
    })


# --- Homepage (Volunteer Opportunities + Application Form) ---
@app.route("/", methods=["GET", "POST"])
def index():
    import json

    if request.method == "POST":
        return _handle_application_post()

    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM opportunities WHERE closed = 0").fetchall()
    conn.close()

    opportunities = dictify_rows(rows)

    # Decode tags JSON for each opportunity
    for opp in opportunities:
        try:
            if isinstance(opp.get("tags"), str):
                opp["tags"] = json.loads(opp["tags"])
        except Exception:
            opp["tags"] = []

    return render_template("index.html", opportunities=opportunities)




# --- Manage (Active Opportunities) ---
@app.route("/manage")
def manage():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM opportunities WHERE closed IS NULL OR closed = 0").fetchall()
    conn.close()
    opportunities = dictify_rows(rows)

    # Fix tags so they show as list, not JSON text
    for o in opportunities:
        try:
            o["tags"] = json.loads(o.get("tags", "[]"))
        except Exception:
            o["tags"] = []

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

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO opportunities 
        (title, time, duration, mode, desc, requirements, location, image, tags, closed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (
        request.form["title"],
        request.form.get("time", ""),
        request.form.get("duration", ""),
        request.form.get("mode", ""),
        request.form.get("desc", ""),
        request.form.get("requirements", ""),
        request.form.get("location", ""),
        image_path if image_path else "default.png",
        tags_json
    ))
    conn.commit()
    conn.close()

    return jsonify({"message": "Opportunity added!"})


# --- Update Opportunity ---
@app.route("/update/<int:opp_id>", methods=["POST"])
def update_opportunity(opp_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Safely parse and re-encode tags
    tags_raw = request.form.get("tags_json") or request.form.get("tags") or "[]"
    try:
        tags = json.loads(tags_raw)
    except Exception:
        tags = []
    tags_json = json.dumps(tags)

    update_fields = (
        request.form["title"],
        request.form.get("time", ""),
        request.form.get("duration", ""),
        request.form.get("mode", ""),
        request.form.get("desc", ""),
        request.form.get("requirements", ""),
        request.form.get("location", ""),
        tags_json,
        opp_id
    )

    cur.execute("""
        UPDATE opportunities 
        SET title=?, time=?, duration=?, mode=?, desc=?, requirements=?, location=?, tags=? 
        WHERE id=?
    """, update_fields)

    # Optional image upload
    if "image" in request.files:
        file = request.files["image"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename).replace(" ", "_").lower()
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            cur.execute("UPDATE opportunities SET image=? WHERE id=?", (filename, opp_id))

    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity updated!"})



# --- Delete Opportunity ---
@app.route("/delete/<int:opp_id>", methods=["POST"])
def delete_opportunity(opp_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM opportunities WHERE id=?", (opp_id,))
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
    conn.execute("UPDATE opportunities SET closed=1, closed_date=? WHERE id=?", 
                 (datetime.now().strftime("%Y-%m-%d %H:%M"), opp_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity closed"})


@app.route("/reopen_opportunity/<int:opp_id>", methods=["POST"])
def reopen_opportunity(opp_id):
    conn = get_db_connection()
    conn.execute("UPDATE opportunities SET closed=0, closed_date=NULL WHERE id=?", (opp_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Opportunity reopened"})


# --- Closed Opportunities ---
@app.route("/closed")
def closed_opportunities():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM opportunities WHERE closed = 1").fetchall()
    conn.close()
    opportunities = dictify_rows(rows)
    return render_template("closed.html", opportunities=opportunities)



# --- View Applicants for Specific Opportunity ---
@app.route("/applicants/<int:opp_id>")
def view_applicants(opp_id):
    import json
    conn = get_db_connection()
    opp = conn.execute("SELECT * FROM opportunities WHERE id=?", (opp_id,)).fetchone()
    conn.close()

    if not opp:
        return "Opportunity not found", 404

    # Convert to dictionary and parse tags JSON if present
    opp_dict = dict(opp)
    try:
        opp_dict["tags"] = json.loads(opp_dict.get("tags", "[]"))
    except Exception:
        opp_dict["tags"] = []

    conn = get_db_connection()
    applicants = conn.execute("SELECT * FROM applications WHERE title=?", (opp_dict["title"],)).fetchall()
    conn.close()

    return render_template("applicants.html", opportunity=opp_dict, applicants=applicants)



# --- Volunteer Check-In ---
@app.route("/check", methods=["GET"])
def check_volunteer():
    email = request.args.get("email", "").strip().lower()
    conn = get_db_connection()
    app_entry = conn.execute("SELECT * FROM applications WHERE LOWER(email)=?", (email,)).fetchone()
    conn.close()
    if app_entry:
        return jsonify({
            "exists": True,
            "first_name": app_entry["first_name"],
            "last_name": app_entry["last_name"],
            "email": app_entry["email"]
        })
    return jsonify({"exists": False})


# --- Review Applications ---
@app.route("/review")
def review():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM applications ORDER BY timestamp DESC").fetchall()
    conn.close()
    apps = dictify_rows(rows)
    return render_template("review.html", applications=apps)



@app.route("/update_status/<int:app_id>", methods=["POST"])
def update_status(app_id):
    new_status = request.form.get("status", "Pending")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db_connection()
    app = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if app:
        history = json.loads(app["history"])
        history.append({"event": f"Status updated to {new_status}", "timestamp": ts})
        conn.execute("UPDATE applications SET status=?, history=? WHERE id=?",
                     (new_status, json.dumps(history), app_id))
        conn.commit()
    conn.close()
    return jsonify({"message": "Status updated successfully"})


# --- Volunteers Overview ---
@app.route("/volunteers")
def volunteers():
    conn = get_db_connection()
    apps = conn.execute("SELECT * FROM applications ORDER BY timestamp DESC").fetchall()
    conn.close()
    return render_template("volunteers.html", applications=apps)


# --- Volunteer Detail ---
@app.route("/volunteer/<int:app_id>")
def volunteer_detail(app_id):
    conn = get_db_connection()
    app = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    conn.close()
    if not app:
        return "Volunteer not found", 404
    return render_template("review_detail.html", app=app)


# --- Add Admin Note ---
@app.route("/add_note/<int:app_id>", methods=["POST"])
def add_note(app_id):
    note_text = request.form.get("note", "").strip()
    if not note_text:
        return jsonify({"message": "Note cannot be empty."})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    app = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if app:
        notes = json.loads(app["notes"])
        history = json.loads(app["history"])
        notes.append({"note": note_text, "timestamp": ts})
        history.append({"event": f"Note added: {note_text}", "timestamp": ts})
        conn.execute("UPDATE applications SET notes=?, history=? WHERE id=?",
                     (json.dumps(notes), json.dumps(history), app_id))
        conn.commit()
    conn.close()
    return jsonify({"message": "Note added successfully."})


if __name__ == "__main__":
    app.run(debug=True)
