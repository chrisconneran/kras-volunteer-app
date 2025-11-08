from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import json, os
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "supersecretkey"

# --- File storage paths ---
DATA_FILE = "opportunities.json"
APPLICATIONS_FILE = "applications.json"
STATIC_FOLDER = "static"
os.makedirs(STATIC_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = STATIC_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


# --- Helpers ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Persistent Data Helpers ---
def load_opportunities():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    # Default starter data
    return [
        {
            "id": 1,
            "title": "Greater - San Francisco Event",
            "time": "6 hours - Thursday - Friday",
            "duration": "2 Days - February 10 -11, 2026",
            "location": "San Francisco - UCSF - Labs - Kickers Annual Event",
            "requirements": "Warm and Friendly attitude",
            "image": "ucsf_event.png",
        },
        {
            "id": 2,
            "title": "Editor - Monthly News Letter",
            "time": "4 hours",
            "duration": "Monthly",
            "location": "Remote via Zoom",
            "requirements": "Ability to pull together in written form an electronic newsletter",
            "image": "newsletter_image.png",
        },
        {
            "id": 3,
            "title": "Booth/Table Volunteer at Conferences",
            "time": "2 - 4 hours",
            "duration": "1 - 2 days depending on conference location",
            "location": "Depends on conference location - may require travel",
            "requirements": "Warm and Friendly attitude",
            "image": "events_asco.jpeg",
        },
        {
            "id": 4,
            "title": "Patient Peer Mentor",
            "time": "2 hours per week",
            "duration": "6 months",
            "location": "Remote phone or text",
            "requirements": "Experience as a patient or caregiver",
            "image": "patient_empowerment.jpeg",
        },
    ]


def save_opportunities(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_applications():
    if os.path.exists(APPLICATIONS_FILE):
        with open(APPLICATIONS_FILE, "r") as f:
            return json.load(f)
    return []


def save_applications(apps):
    with open(APPLICATIONS_FILE, "w") as f:
        json.dump(apps, f, indent=2)


# --- Load initial data ---
OPPORTUNITIES = load_opportunities()
APPLICATIONS = load_applications()


# --- Shared POST handler for volunteer application submissions ---
def _handle_application_post():
    form_data = request.form.to_dict()
    form_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Assign unique ID and defaults
    form_data["id"] = len(APPLICATIONS) + 1
    form_data["status"] = "Pending"
    form_data.setdefault("history", []).append({
        "event": "Application submitted",
        "timestamp": form_data["timestamp"]
    })
    form_data.setdefault("notes", [])

    # Add opportunity title for modal confirmation
    form_data["opportunity_title"] = request.form.get("opportunity_title", "Volunteer Opportunity")

    # Save to applications.json
    APPLICATIONS.append(form_data)
    save_applications(APPLICATIONS)

    # Return JSON for AJAX confirmation modal
    return jsonify({
        "message": "Application submitted successfully!",
        "title": form_data["opportunity_title"]
    })



# --- MENU PAGE (homepage) ---
# Accept POST here so forms that post to "/" won't 405.
@app.route("/", methods=["GET", "POST"])
def menu():
    if request.method == "POST":
        return _handle_application_post()
    return render_template("menu.html")


# --- Volunteer Application Form ---
@app.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        return _handle_application_post()

    active_opps = [o for o in OPPORTUNITIES if not o.get("closed")]
    return render_template("apply.html", opportunities=active_opps)


# --- Manage (Active only) ---
@app.route("/manage", methods=["GET"])
def manage():
    active_opps = [o for o in OPPORTUNITIES if not o.get("closed")]
    return render_template("manage.html", opportunities=active_opps)


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

    new_opp = {
        "id": len(OPPORTUNITIES) + 1,
        "title": request.form["title"],
        "time": request.form.get("time", ""),
        "duration": request.form.get("duration", ""),
        "mode": request.form.get("mode", ""),
        "desc": request.form.get("desc", ""),
        "requirements": request.form.get("requirements", ""),
        "location": request.form.get("location", ""),
        "image": image_path if image_path else "default.png",
        "tags": tags,
        "closed": False
    }

    OPPORTUNITIES.append(new_opp)
    save_opportunities(OPPORTUNITIES)
    return jsonify({"message": "Opportunity added!"})


# --- Update Opportunity ---
@app.route("/update/<int:opp_id>", methods=["POST"])
def update_opportunity(opp_id):
    for opp in OPPORTUNITIES:
        if opp["id"] == opp_id:
            tags_json = request.form.get("tags_json") or request.form.get("tags") or "[]"
            try:
                tags = json.loads(tags_json)
            except Exception:
                tags = []

            opp.update({
                "title": request.form["title"],
                "time": request.form.get("time", ""),
                "duration": request.form.get("duration", ""),
                "mode": request.form.get("mode", ""),
                "desc": request.form.get("desc", ""),
                "requirements": request.form.get("requirements", ""),
                "location": request.form.get("location", ""),
                "tags": tags
            })

            if "image" in request.files:
                file = request.files["image"]
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename).replace(" ", "_").lower()
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    opp["image"] = filename

            save_opportunities(OPPORTUNITIES)
            return jsonify({"message": "Opportunity updated!"})
    return jsonify({"error": "Opportunity not found"}), 404


# --- Delete Opportunity ---
@app.route("/delete/<int:opp_id>", methods=["POST"])
def delete_opportunity(opp_id):
    global OPPORTUNITIES
    before = len(OPPORTUNITIES)
    OPPORTUNITIES = [o for o in OPPORTUNITIES if o.get("id") != opp_id]
    if len(OPPORTUNITIES) == before:
        return jsonify({"error": "Opportunity not found"}), 404
    save_opportunities(OPPORTUNITIES)
    return jsonify({"message": "Opportunity deleted"})


# --- Close / Reopen ---
@app.route("/close_opportunity/<int:opp_id>", methods=["POST"])
def close_opportunity(opp_id):
    for opp in OPPORTUNITIES:
        if opp["id"] == opp_id:
            opp["closed"] = True
            opp["closed_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_opportunities(OPPORTUNITIES)
            return jsonify({"message": f"{opp['title']} marked as closed."})
    return jsonify({"error": "Opportunity not found"}), 404


@app.route("/reopen_opportunity/<int:opp_id>", methods=["POST"])
def reopen_opportunity(opp_id):
    for opp in OPPORTUNITIES:
        if opp["id"] == opp_id:
            opp["closed"] = False
            opp.pop("closed_date", None)
            save_opportunities(OPPORTUNITIES)
            return jsonify({"message": f"{opp['title']} reopened successfully."})
    return jsonify({"error": "Opportunity not found"}), 404


# --- Closed Opportunities ---
@app.route("/closed")
def closed_opportunities():
    closed = [o for o in OPPORTUNITIES if o.get("closed")]
    apps = load_applications()
    for opp in closed:
        opp["volunteers"] = [a for a in apps if a.get("title") == opp["title"]]
    return render_template("closed.html", opportunities=closed)

# --- View Applicants for a Specific Opportunity ---
@app.route("/applicants/<int:opp_id>")
def view_applicants(opp_id):
    opportunity = next((o for o in OPPORTUNITIES if o["id"] == opp_id), None)
    if not opportunity:
        return "Opportunity not found", 404

    apps = load_applications()
    applicants = [a for a in apps if a.get("title") == opportunity["title"]]
    return render_template("applicants.html", opportunity=opportunity, applicants=applicants)


# --- Volunteer Check-In ---
@app.route("/check", methods=["GET"])
def check_volunteer():
    email = request.args.get("email", "").strip().lower()
    for app_entry in APPLICATIONS:
        if app_entry.get("email", "").lower() == email:
            return jsonify({
                "exists": True,
                "first_name": app_entry.get("first_name", ""),
                "last_name": app_entry.get("last_name", ""),
                "email": app_entry.get("email", "")
            })
    return jsonify({"exists": False})


# --- Review & Assignments ---
@app.route("/review")
def review():
    apps = load_applications()
    apps.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return render_template("review.html", applications=apps)


@app.route("/update_status/<int:app_id>", methods=["POST"])
def update_status(app_id):
    apps = load_applications()
    new_status = request.form.get("status", "Pending")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    for a in apps:
        if a["id"] == app_id:
            a["status"] = new_status
            a.setdefault("history", []).append({
                "event": f"Status updated to {new_status}",
                "timestamp": ts
            })
            break
    save_applications(apps)
    return jsonify({"message": "Status updated successfully"})


# --- Volunteers Overview ---
@app.route("/volunteers")
def volunteers():
    apps = load_applications()
    apps.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return render_template("volunteers.html", applications=apps)


# --- Volunteer Detail ---
@app.route("/volunteer/<int:app_id>")
def volunteer_detail(app_id):
    apps = load_applications()
    app_entry = next((a for a in apps if a["id"] == app_id), None)
    if not app_entry:
        return "Volunteer not found", 404
    return render_template("review_detail.html", app=app_entry)


# --- Admin Notes ---
@app.route("/add_note/<int:app_id>", methods=["POST"])
def add_note(app_id):
    note_text = request.form.get("note", "").strip()
    apps = load_applications()
    for a in apps:
        if a["id"] == app_id and note_text:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            a.setdefault("notes", []).append({"note": note_text, "timestamp": ts})
            a.setdefault("history", []).append({
                "event": f"Note added: {note_text}",
                "timestamp": ts
            })
            break
    save_applications(apps)
    return jsonify({"message": "Note added successfully."})


if __name__ == "__main__":
    app.run(debug=True)
