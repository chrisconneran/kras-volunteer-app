import os
import base64
import psycopg
from psycopg.rows import dict_row

# Set this to your Render DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")

STATIC_FOLDER = "static"  # same as your Flask config


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def file_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def migrate():
    print("Starting base64 image migration...")

    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # Load all opportunities that have file-based images
            cur.execute("""
                SELECT id, image, image_base64
                FROM opportunities
                ORDER BY id
            """)
            rows = cur.fetchall()

            updated_count = 0
            skipped_count = 0
            missing_file_count = 0

            for row in rows:
                opp_id = row["id"]
                filename = row["image"]
                existing_b64 = row["image_base64"]

                # Skip if already migrated
                if existing_b64 and existing_b64.strip() != "":
                    skipped_count += 1
                    continue

                # Skip if no filename present
                if not filename or filename.strip() == "":
                    missing_file_count += 1
                    continue

                # Build full path
                file_path = os.path.join(STATIC_FOLDER, filename)

                if not os.path.exists(file_path):
                    print(f"[WARNING] File missing on disk: {file_path}")
                    missing_file_count += 1
                    continue

                # Convert file → base64
                try:
                    encoded = file_to_base64(file_path)
                except Exception as e:
                    print(f"[ERROR] Failed to read {file_path}: {e}")
                    missing_file_count += 1
                    continue

                # Save base64 to DB
                cur.execute("""
                    UPDATE opportunities
                    SET image_base64 = %s
                    WHERE id = %s
                """, (encoded, opp_id))

                updated_count += 1

            conn.commit()

            print("Migration complete.")
            print(f"Converted and saved base64 images: {updated_count}")
            print(f"Already migrated / skipped: {skipped_count}")
            print(f"Missing or unreadable files: {missing_file_count}")


if __name__ == "__main__":
    migrate()
