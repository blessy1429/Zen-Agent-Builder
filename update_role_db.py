import sqlite3

conn = sqlite3.connect("users.db")

cursor = conn.cursor()

cursor.execute("""
ALTER TABLE roles
ADD COLUMN status TEXT DEFAULT 'Active'
""")

conn.commit()

conn.close()

print("Role status column added successfully!")