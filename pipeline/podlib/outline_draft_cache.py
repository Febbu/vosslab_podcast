import hashlib
import json
import os
import re


REPO_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


#============================================
def repo_slug(repo_full_name: str) -> str:
	"""
	Build filesystem-safe slug for one repo full name.
	"""
	text = (repo_full_name or "").strip().lower().replace("/", "__")
	text = REPO_SLUG_RE.sub("-", text).strip("-")
	if not text:
		return "unknown_repo"
	return text


#============================================
def compute_run_fingerprint(
	outline: dict,
	stage_name: str,
	target_value: int,
	extra: dict | None = None,
) -> str:
	"""
	Compute stable hash key for one generation run context.
	"""
	payload = {
		"stage_name": stage_name,
		"user": outline.get("user", ""),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"target_value": target_value,
		"totals": outline.get("totals", {}),
		"extra": extra or {},
	}
	encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
	return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


#============================================
def build_cache_path(cache_dir: str, repo_full_name: str, run_fingerprint: str) -> str:
	"""
	Build cache JSON path for one repo draft.
	"""
	filename = f"{repo_slug(repo_full_name)}_{run_fingerprint}.json"
	return os.path.join(cache_dir, filename)


#============================================
def load_cached_draft(path: str) -> dict | None:
	"""
	Load one cached draft payload from JSON path.
	"""
	if not os.path.isfile(path):
		return None
	try:
		with open(path, "r", encoding="utf-8") as handle:
			payload = json.load(handle)
	except Exception:
		return None
	if not isinstance(payload, dict):
		return None
	return payload


#============================================
def save_cached_draft(path: str, payload: dict) -> None:
	"""
	Write one cached draft payload to disk.
	"""
	cache_dir = os.path.dirname(path)
	if cache_dir:
		os.makedirs(cache_dir, exist_ok=True)
	with open(path, "w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
		handle.write("\n")
