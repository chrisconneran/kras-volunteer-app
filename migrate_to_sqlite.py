import sqlite3
import json

DB_FILE = "volunteers.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- Load existing JSON data ---
with open("opportunities.json", "r") as f:
    opportunities = json.load(f)

with open("applications.json", "r") as f:
    applications = json.load(f)

conn = get_db_connection()
cur = conn.cursor()

# --- Clear any existing data in case you run again ---
cur.execute("DELETE FROM opportunities")
cur.execute("DELETE FROM applications")

# --- Insert opportunities ---
for opp in opportunities:
    cur.execute("""
        INSERT INTO opportunities
        (id, title, time, duration, location, requirements, image, tags, closed, closed_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        opp.get("id"),
        opp.get("title"),
        opp.get("time"),
        opp.get("duration"),
        opp.get("location"),
        opp.get("requirements"),
        opp.get("image"),
        json.dumps(opp.get("tags", [])),
        int(opp.get("closed", False)),
        opp.get("closed_date")
    ))

# --- Insert applications ---
for app in applications:
    cur.execute("""
        INSERT INTO applications
        (id, first_name, last_name, email, phone, contact, title, time, duration, location,
         comments, status, timestamp, history, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app.get("id"),
        app.get("first_name"),
        app.get("last_name"),
        app.get("email"),
        app.get("phone"),
        app.get("contact"),
        app.get("title"),
        app.get("time"),
        app.get("duration"),
        app.get("location"),
        app.get("comments"),
        app.get("status"),
        app.get("timestamp"),
        json.dumps(app.get("history", [])),
        json.dumps(app.get("notes", []))
    ))

conn.commit()
conn.close()

print("✅ Migration complete: Data imported into volunteers.db")
