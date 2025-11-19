import psycopg

DB_URL = "postgresql://kras_volunteer_db_user:vmpTCrcXeuB3je90aJBkBM1OPgRzlGKS@dpg-d4ecfufpm1nc738p2ag0-a.ohio-postgres.render.com/kras_volunteer_db"


def fix_sequences():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Fix applications IDs
            cur.execute(
                """
                SELECT setval(
                    'applications_id_seq',
                    COALESCE((SELECT MAX(id) FROM applications), 1)
                );
                """
            )

            # Fix opportunities IDs
            cur.execute(
                """
                SELECT setval(
                    'opportunities_id_seq',
                    COALESCE((SELECT MAX(id) FROM opportunities), 1)
                );
                """
            )

        conn.commit()

    print("Postgres sequences are repaired.")


if __name__ == "__main__":
    fix_sequences()
