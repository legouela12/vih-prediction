import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database.connection import test_connection, SQLALCHEMY_DATABASE_URL

print('DB URL:', SQLALCHEMY_DATABASE_URL)
ok, err = test_connection()
print('OK:', ok)
print('ERR:', err)
