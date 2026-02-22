import hashlib
import json
import os
from datetime import datetime
from datetime import timezone


#============================================
class GitHubQueryCache:
	"""
	Filesystem-backed cache for GitHub query payloads.
	"""

	def __init__(self, cache_dir: str, default_ttl_seconds: int):
		self.cache_dir = os.path.abspath(cache_dir)
		self.default_ttl_seconds = int(default_ttl_seconds)
		os.makedirs(self.cache_dir, exist_ok=True)

	#============================================
	def _cache_key_text(self, category: str, query: dict) -> str:
		payload = {
			"category": category,
			"query": query,
		}
		return json.dumps(payload, sort_keys=True, ensure_ascii=True)

	#============================================
	def _cache_path(self, category: str, query: dict) -> str:
		key_text = self._cache_key_text(category, query)
		hash_text = hashlib.sha256(key_text.encode("utf-8")).hexdigest()
		return os.path.join(self.cache_dir, f"{category}_{hash_text}.json")

	#============================================
	def get(self, category: str, query: dict, ttl_seconds: int | None = None):
		if ttl_seconds is None:
			ttl_seconds = self.default_ttl_seconds
		cache_path = self._cache_path(category, query)
		if not os.path.isfile(cache_path):
			return None
		try:
			with open(cache_path, "r", encoding="utf-8") as handle:
				payload = json.load(handle)
		except Exception:
			return None
		if not isinstance(payload, dict):
			return None
		fetched_at_text = str(payload.get("fetched_at", "")).strip()
		if not fetched_at_text:
			return None
		try:
			fetched_at = datetime.fromisoformat(fetched_at_text.replace("Z", "+00:00"))
		except Exception:
			return None
		if fetched_at.tzinfo is None:
			fetched_at = fetched_at.replace(tzinfo=timezone.utc)
		age_seconds = (datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc)).total_seconds()
		if age_seconds < 0:
			return None
		if ttl_seconds >= 0 and age_seconds > ttl_seconds:
			return None
		return payload.get("data")

	#============================================
	def set(self, category: str, query: dict, data) -> str:
		cache_path = self._cache_path(category, query)
		payload = {
			"category": category,
			"query": query,
			"fetched_at": datetime.now(timezone.utc).isoformat(),
			"data": data,
		}
		with open(cache_path, "w", encoding="utf-8") as handle:
			json.dump(payload, handle, ensure_ascii=True, sort_keys=True, indent=2)
			handle.write("\n")
		return cache_path
