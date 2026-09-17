"""Volatile interview state only. Never writes caregiver data to disk."""
import copy
import time

class Store:
 def __init__(self, directory=None, ttl_seconds=1800):
  # directory is accepted for compatibility with development test setup, never used.
  self.ttl_seconds=ttl_seconds
  self.sessions={}
 def put(self,s):
  self.sessions[s['id']]=(time.monotonic(),copy.deepcopy(s))
 def get(self,sid,owner):
  self.expire()
  record=self.sessions.get(sid)
  return copy.deepcopy(record[1]) if record and record[1]['owner']==owner else None
 def list(self,owner):
  self.expire()
  return [copy.deepcopy(s) for _,s in self.sessions.values() if s['owner']==owner]
 def delete(self,sid,owner):
  record=self.sessions.get(sid)
  if record and record[1]['owner']==owner:self.sessions.pop(sid,None)
 def expire(self):
  cutoff=time.monotonic()-self.ttl_seconds
  for sid,(updated,_) in list(self.sessions.items()):
   if updated<=cutoff:self.sessions.pop(sid,None)
 def recover(self):
  # Restarting the service creates an empty store; there is nothing to recover.
  pass
 def clear(self):self.sessions.clear()
