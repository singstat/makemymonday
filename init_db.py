import psycopg2, os

DB_URL = os.getenv("DATABASE_URL")

def init_db():
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            with open("schema.sql", "r", encoding="utf-8") as f:
                cur.execute(f.read())
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("DB schema created ✅")
