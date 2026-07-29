param(
    [int]$Top = 30
)

$db = "D:\CW700S\AI\cw700s_ai.db"
$python = "D:\CW700S\AI\.venv\Scripts\python.exe"

if (-not (Test-Path $db)) {
    throw "数据库不存在：$db"
}

$code = @'
import sqlite3
import sys

db = sys.argv[1]
top = int(sys.argv[2])

con = sqlite3.connect(db)
rows = con.execute(
    """
    SELECT analyzed_at, primary_category, max_confidence, relative_path
    FROM video_analysis
    WHERE status = 'ok'
    ORDER BY analyzed_at DESC
    LIMIT ?
    """,
    (top,),
).fetchall()

for analyzed_at, category, confidence, path in rows:
    print(f"{analyzed_at} | {category:<12} | {confidence:.2f} | {path}")

con.close()
'@

& $python -c $code $db $Top
