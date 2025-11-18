import sqlite3
import psycopg
import os
import json

# Full path to your SQLite database file
SQLITE_DB = r"C:\Users\Chris\OneDrive\Documentos\School\2025 - Fall\System Analysis in Healthcare\Team Project\volunteers.db"

# Postgres connection URL from environment (Render DATABASE_URL)
POSTGRES_URL = "postgres://kras_volunteer_db_user:vmpTCrcXeuB3je90aJBkBM1OPgRzlGKS@dpg-d4ecfufpm1nc738p2ag0-a.ohio-postgres.render.com/kras_volunteer_db"



def fetch_all_sqlite(query, params=None):
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params or [])
    rows = cur.fetchall()
    conn.close()
    return rows


def insert_applications(pg_conn):
    print("Migrating applications...")

    rows = fetch_all_sqlite("SELECT * FROM applications")

    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO applications
                (id, first_name, last_name, email, phone, contact, title, time, duration,
                 location, comments, status, timestamp, history, notes, mode, is_champion)
                VALUES
                (%(id)s, %(first_name)s, %(last_name)s, %(email)s, %(phone)s, %(contact)s,
                 %(title)s, %(time)s, %(duration)s, %(location)s, %(comments)s, %(status)s,
                 %(timestamp)s, %(history)s, %(notes)s, %(mode)s, %(is_champion)s)
                """,
                {
                    "id": row["id"],
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "email": row["email"],
                    "phone": row["phone"],
                    "contact": row["contact"],
                    "title": row["title"],
                    "time": row["time"],
                    "duration": row["duration"],
                    "location": row["location"],
                    "comments": row["comments"],
                    "status": row["status"],
                    "timestamp": row["timestamp"],
                    "history": row["history"],
                    "notes": row["notes"],
                    "mode": row["mode"],
                    "is_champion": bool(row["is_champion"]) if row["is_champion"] is not None else False,
                },
            )

    print(f"Inserted {len(rows)} applications.")


def insert_opportunities(pg_conn):
    print("Migrating opportunities...")

    rows = fetch_all_sqlite("SELECT * FROM opportunities")

    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO opportunities
                (id, title, time, duration, location, requirements, image, tags,
                 closed, closed_date, description, mode)
                VALUES
                (%(id)s, %(title)s, %(time)s, %(duration)s, %(location)s,
                 %(requirements)s, %(image)s, %(tags)s,
                 %(closed)s, %(closed_date)s, %(description)s, %(mode)s)
                """,
                {
                    "id": row["id"],
                    "title": row["title"],
                    "time": row["time"],
                    "duration": row["duration"],
                    "location": row["location"],
                    "requirements": row["requirements"],
                    "image": row["image"],
                    "tags": row["tags"],
                    "closed": bool(row["closed"]) if row["closed"] is not None else False,
                    "closed_date": row["closed_date"],
                    "description": row["desc"],
                    "mode": row["mode"],
                },
            )

    print(f"Inserted {len(rows)} opportunities.")


def insert_champions_opportunities(pg_conn):
    print("Migrating champion assignments...")

    rows = fetch_all_sqlite("SELECT * FROM champions_opportunities")

    with pg_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO champions_opportunities
                (id, champion_id, opportunity_id)
                VALUES (%s, %s, %s)
                """,
                (row["id"], row["champion_id"], row["opportunity_id"]),
            )

    print(f"Inserted {len(rows)} champion assignments.")


def main():
    print("Connecting to Postgres...")
    pg_conn = psycopg.connect(POSTGRES_URL)
    pg_conn.autocommit = True

    insert_applications(pg_conn)
    insert_opportunities(pg_conn)
    insert_champions_opportunities(pg_conn)

    pg_conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
