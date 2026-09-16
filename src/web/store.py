"""Encrypted local pilot storage. No transcripts or audio in repository/logs."""
import json, os, sqlite3, time
from pathlib import Path
from cryptography.fernet import Fernet

class Store:
 def __init__(self, directory):
  self.directory=Path(directory).expanduser().resolve()
  repo=Path(__file__).resolve().parents[2]
  if self.directory.is_relative_to(repo) or 'CloudStorage' in self.directory.parts:
   raise RuntimeError('ASDWISE_DATA_DIR must be outside the synced source repository.')
  self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
  os.chmod(self.directory,0o700)
  key=self.directory/'storage.key'
  if not key.exists():
   fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
  self.cipher=Fernet(key.read_bytes())
  self.path=self.directory/'sessions.sqlite3'
  with self.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, owner TEXT, updated REAL, payload BLOB)')
  os.chmod(self.path,0o600)
 def connect(self):return sqlite3.connect(self.path,timeout=10)
 def put(self,s):
  with self.connect() as db:
   db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)',(s['id'],s['owner'],time.time(),self.cipher.encrypt(json.dumps(s).encode())))
 def get(self,sid,owner):
  with self.connect() as db:
   row=db.execute('SELECT payload FROM sessions WHERE id=? AND owner=?',(sid,owner)).fetchone()
  return json.loads(self.cipher.decrypt(row[0])) if row else None
 def list(self,owner):
  with self.connect() as db:
   rows=db.execute('SELECT payload FROM sessions WHERE owner=? ORDER BY updated DESC',(owner,)).fetchall()
  return [json.loads(self.cipher.decrypt(r[0])) for r in rows]
 def delete(self,sid,owner):
  with self.connect() as db:db.execute('DELETE FROM sessions WHERE id=? AND owner=?',(sid,owner))
 def expire(self):
  with self.connect() as db:db.execute('DELETE FROM sessions WHERE updated < ?',(time.time()-7*86400,))
 def recover(self):
  with self.connect() as db:rows=db.execute('SELECT payload FROM sessions').fetchall()
  for row in rows:
   s=json.loads(self.cipher.decrypt(row[0]))
   if s.get('report_status')=='generating':
    s['report_status']='failed';s['report_error']='Generation was interrupted by a server restart. Please retry.';self.put(s)
