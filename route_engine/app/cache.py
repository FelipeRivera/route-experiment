import json
import hashlib
from redis import Redis

class Cache:
    def __init__(self, host, port, db=0):
        self.r = Redis(host=host, port=port, db=db)

    def _key(self, city, src, dst, constraints):
        payload = json.dumps({"city": city, "src": src, "dst": dst, "c": constraints}, sort_keys=True)
        return "route:" + hashlib.sha256(payload.encode()).hexdigest()

    def get(self, city, src, dst, constraints):
        key = self._key(city, src, dst, constraints)
        raw = self.r.get(key)
        if raw:
            return json.loads(raw)
        return None

    def set(self, city, src, dst, constraints, value, ttl=3600):
        key = self._key(city, src, dst, constraints)
        self.r.setex(key, ttl, json.dumps(value))
