from database import engine
from sqlalchemy import text

with engine.connect() as conn:

    try:
        conn.execute(
            text(
                """
                ALTER TABLE agents
                ADD COLUMN description TEXT
                """
            )
        )

        conn.commit()

        print("description column added successfully!")

    except Exception as e:
        print("Error:", e)