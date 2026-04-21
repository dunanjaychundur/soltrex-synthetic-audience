import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print('=== EDUCATION ===')
cur.execute("SELECT DISTINCT education, COUNT(*) as cnt FROM nemotron_personas GROUP BY education ORDER BY cnt DESC LIMIT 10")
for r in cur.fetchall(): print(r)

print('=== SEX ===')
cur.execute("SELECT DISTINCT sex, COUNT(*) as cnt FROM nemotron_personas GROUP BY sex")
for r in cur.fetchall(): print(r)

print('=== STATE sample ===')
cur.execute("SELECT DISTINCT state, COUNT(*) as cnt FROM nemotron_personas GROUP BY state ORDER BY cnt DESC LIMIT 10")
for r in cur.fetchall(): print(r)

print('=== OCCUPATION sample ===')
cur.execute("SELECT DISTINCT occupation FROM nemotron_personas WHERE occupation IS NOT NULL LIMIT 20")
for r in cur.fetchall(): print(r)

print('=== HOBBIES sample ===')
cur.execute("SELECT hobbies_and_interests FROM nemotron_personas WHERE hobbies_and_interests IS NOT NULL LIMIT 5")
for r in cur.fetchall(): print(r[0][:150])

print('=== PERSONA sample ===')
cur.execute("SELECT persona FROM nemotron_personas WHERE persona IS NOT NULL LIMIT 3")
for r in cur.fetchall(): print(r[0][:200])
print('---')

cur.close()
conn.close()