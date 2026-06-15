import psycopg2
from psycopg2.extras import RealDictCursor
import time

while True:
    try:
        connection = psycopg2.connect(
            host="localhost",
            database="face-detection-db",
            user="postgres",
            password="1234",
            cursor_factory=RealDictCursor,
        )
        # Each SQL statement is its own transaction — a failed statement
        # won't abort subsequent queries on the same connection.
        connection.autocommit = True
        cursor = connection.cursor()

        print("successfully connected:", cursor)
        break
    except Exception as Error:
        print("Database connection failed!!!")
        print("error:", Error)
        time.sleep(2)