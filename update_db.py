import sqlite3

conn = sqlite3.connect("users.db")

cursor = conn.cursor()

cursor.execute("""
ALTER TABLE modules
ADD COLUMN status TEXT DEFAULT 'Active'
""")

conn.commit()

conn.close()

print("Status column added successfully!")
