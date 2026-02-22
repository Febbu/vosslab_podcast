import random
import time
from datetime import datetime
from datetime import timezone

from podlib import github_cache

#============================================
class RateLimitError(RuntimeError):
	"""
	Raised when GitHub API rate limits block further requests.
	"""


#============================================
class GitHubClient:
	"""
	Thin PyGithub wrapper for fetch pipeline use-cases.
	"""

	def __init__(self, token: str, log_fn=None):
		self.log_fn = log_fn
		self._rate_check_count = 0
		self._low_remaining_threshold = 5
		self._max_proactive_sleep_seconds = 10
		self._api_call_count = 0
		self._api_calls_by_context: dict[str, int] = {}
		self._cache_hit_count = 0
		self._cache_miss_count = 0
		self.cache = github_cache.GitHubQueryCache(
			cache_dir="out/cache/github_api",
			default_ttl_seconds=24 * 60 * 60,
		)
		try:
			from github import Github
			from github.GithubException import GithubException
		except ModuleNotFoundError as error:
			raise RuntimeError(
				"Missing dependency: PyGithub. Install it with pip install PyGithub."
			) from error
		self._github_exception_class = GithubException
		self.client = self._build_github_client(Github, token)

	#============================================
	def _build_github_client(self, github_class, token: str):
		"""
		Create Github client with retry disabled when supported.
		"""
		if token:
			try:
				return github_class(token, retry=None)
			except TypeError:
				return github_class(token)
		try:
			return github_class(retry=None)
		except TypeError:
			return github_class()

	#============================================
	def log(self, message: str) -> None:
		"""
		Emit one log line when logger is configured.
		"""
		if self.log_fn is not None:
			self.log_fn(message)

	#============================================
	def record_api_call(self, context: str) -> None:
		"""
		Track one outbound GitHub API call.
		"""
		if not hasattr(self, "_api_call_count"):
			self._api_call_count = 0
		if not hasattr(self, "_api_calls_by_context"):
			self._api_calls_by_context = {}
		self._api_call_count += 1
		if context not in self._api_calls_by_context:
			self._api_calls_by_context[context] = 0
		self._api_calls_by_context[context] += 1

	#============================================
	def api_usage_snapshot(self) -> dict:
		"""
		Return API/caching counters for reporting.
		"""
		if not hasattr(self, "_api_call_count"):
			self._api_call_count = 0
		if not hasattr(self, "_api_calls_by_context"):
			self._api_calls_by_context = {}
		if not hasattr(self, "_cache_hit_count"):
			self._cache_hit_count = 0
		if not hasattr(self, "_cache_miss_count"):
			self._cache_miss_count = 0
		return {
			"api_call_count": self._api_call_count,
			"api_calls_by_context": dict(self._api_calls_by_context),
			"cache_hit_count": self._cache_hit_count,
			"cache_miss_count": self._cache_miss_count,
		}

	#============================================
	def normalize_datetime(self, value: datetime) -> datetime:
		"""
		Normalize datetime to timezone-aware UTC.
		"""
		if value.tzinfo is None:
			return value.replace(tzinfo=timezone.utc)
		return value.astimezone(timezone.utc)

	#============================================
	def parse_rate_limit_reset(self, reset_value) -> datetime:
		"""
		Normalize PyGithub reset values to timezone-aware UTC datetime.
		"""
		if isinstance(reset_value, datetime):
			return self.normalize_datetime(reset_value)
		if isinstance(reset_value, (int, float)):
			return datetime.fromtimestamp(float(reset_value), tz=timezone.utc)
		if isinstance(reset_value, str):
			return datetime.fromisoformat(reset_value.replace("Z", "+00:00"))
		raise RuntimeError(f"Unsupported rate-limit reset value: {reset_value!r}")

	#============================================
	def get_core_rate_limit_snapshot(self) -> tuple[int, datetime]:
		"""
		Read core rate-limit remaining/reset across PyGithub versions.
		"""
		self.record_api_call("GET /rate_limit")
		overview = self.client.get_rate_limit()
		rate_limit = getattr(overview, "core", None)
		if rate_limit is None:
			resources = getattr(overview, "resources", None)
			if isinstance(resources, dict):
				rate_limit = resources.get("core")
			elif resources is not None:
				rate_limit = getattr(resources, "core", None)
		if rate_limit is None:
			raise RuntimeError("Rate limit data does not expose core resource fields.")
		remaining = int(getattr(rate_limit, "remaining"))
		reset_time = self.parse_rate_limit_reset(getattr(rate_limit, "reset"))
		return remaining, reset_time

	#============================================
	def maybe_wait_for_rate_limit(self, context: str, force: bool = False) -> None:
		"""
		Sleep until reset when rate limit is very low.
		"""
		self._rate_check_count += 1
		if (not force) and (self._rate_check_count % 15 != 0):
			return
		try:
			remaining, reset_time = self.get_core_rate_limit_snapshot()
		except Exception as error:
			self.log(f"Rate limit check ({context}) unavailable: {error}")
			return
		self.log(
			f"Rate limit check ({context}): remaining={remaining}, "
			+ f"reset_at={reset_time.isoformat()}"
		)
		if remaining > self._low_remaining_threshold:
			return
		sleep_seconds = int((reset_time - datetime.now(timezone.utc)).total_seconds()) + 1
		if sleep_seconds <= 0:
			return
		if sleep_seconds > self._max_proactive_sleep_seconds:
			self.log(
				"Rate limit is low, but proactive wait exceeds cap "
				+ f"({sleep_seconds}s > {self._max_proactive_sleep_seconds}s); "
				+ "skipping proactive sleep and continuing."
			)
			return
		self.log(
			f"Rate limit is low ({remaining}); sleeping {sleep_seconds}s until reset."
		)
		time.sleep(sleep_seconds)

	#============================================
	def sleep_request_jitter(self, context: str) -> None:
		"""
		Add small random jitter before API calls.
		"""
		delay = random.random()
		time.sleep(delay)

	#============================================
	def call_with_retry(self, context: str, call_fn):
		"""
		Run one API call with jitter.
		"""
		self.sleep_request_jitter(context)
		try:
			self.record_api_call(context)
			return call_fn()
		except self._github_exception_class as error:
			self.raise_from_github_error(error, context)

	#============================================
	def cached_query(
		self,
		category: str,
		query: dict,
		context: str,
		call_fn,
		ttl_seconds: int | None = None,
	):
		"""
		Resolve one query through filesystem cache plus API fallback.
		"""
		cached = self.cache.get(category, query, ttl_seconds=ttl_seconds)
		if cached is not None:
			self._cache_hit_count += 1
			self.log(f"GitHub cache hit [{category}]")
			return cached
		self._cache_miss_count += 1
		self.log(f"GitHub cache miss [{category}]")
		data = self.call_with_retry(context, call_fn)
		self.cache.set(category, query, data)
		return data

	#============================================
	def raise_from_github_error(self, error: Exception, context: str) -> None:
		"""
		Raise a human-readable rate-limit error or re-raise original.
		"""
		status = getattr(error, "status", None)
		if status != 403:
			raise error
		reset_text = "unknown"
		remaining_text = "unknown"
		try:
			remaining, reset_time = self.get_core_rate_limit_snapshot()
			reset_text = reset_time.isoformat()
			remaining_text = str(remaining)
		except Exception:
			pass
		raise RateLimitError(
			"GitHub API rate limit exceeded while "
			+ f"{context}; remaining={remaining_text}; reset_at={reset_text}. "
			+ "Provide settings.yaml github.token for higher limits."
		)

	#============================================
	def list_repos(self, user: str):
		"""
		List owner repositories sorted by updated timestamp.
		"""
		self.maybe_wait_for_rate_limit("list_repos", force=True)
		return self.cached_query(
			"list_repos",
			{"user": user, "type": "owner", "sort": "updated", "direction": "desc"},
			f"GET /users/{user}/repos",
			lambda: [
				getattr(repo_obj, "raw_data", {}) or {}
				for repo_obj in self.client.get_user(user).get_repos(
					type="owner",
					sort="updated",
					direction="desc",
				)
			],
		)

	#============================================
	def list_commits(self, repo_full_name: str, since: datetime, until: datetime):
		"""
		List repository commits inside time window.
		"""
		self.maybe_wait_for_rate_limit(f"list_commits {repo_full_name}")
		since_iso = self.normalize_datetime(since).isoformat()
		until_iso = self.normalize_datetime(until).isoformat()
		return self.cached_query(
			"list_commits",
			{
				"repo_full_name": repo_full_name,
				"since": since_iso,
				"until": until_iso,
			},
			f"GET /repos/{repo_full_name}/commits",
			lambda: self._list_commits_live(repo_full_name, since, until),
		)

	#============================================
	def list_issues(self, repo_full_name: str, since: datetime):
		"""
		List repository issues and pull requests updated since window start.
		"""
		self.maybe_wait_for_rate_limit(f"list_issues {repo_full_name}")
		since_iso = self.normalize_datetime(since).isoformat()
		return self.cached_query(
			"list_issues",
			{
				"repo_full_name": repo_full_name,
				"since": since_iso,
			},
			f"GET /repos/{repo_full_name}/issues",
			lambda: self._list_issues_live(repo_full_name, since),
		)

	#============================================
	def get_repo(self, full_name: str):
		"""
		Get one repository object by full name.
		"""
		self.maybe_wait_for_rate_limit(f"get_repo {full_name}")
		return self.call_with_retry(
			f"GET /repos/{full_name}",
			lambda: self.client.get_repo(full_name),
		)

	#============================================
	def _list_commits_live(self, repo_full_name: str, since: datetime, until: datetime) -> list[dict]:
		"""
		Fetch commit raw payloads from live API.
		"""
		repo_obj = self.get_repo(repo_full_name)
		return [
			getattr(commit_obj, "raw_data", {}) or {}
			for commit_obj in repo_obj.get_commits(since=since, until=until)
		]

	#============================================
	def _list_issues_live(self, repo_full_name: str, since: datetime) -> list[dict]:
		"""
		Fetch issue raw payloads from live API.
		"""
		repo_obj = self.get_repo(repo_full_name)
		return [
			getattr(issue_obj, "raw_data", {}) or {}
			for issue_obj in repo_obj.get_issues(
				state="all",
				since=since,
				sort="updated",
				direction="desc",
			)
		]

	#============================================
	def get_file_content(self, repo_full_name: str, path: str, ref: str) -> dict | None:
		"""
		Get one file content payload with metadata.
		"""
		self.maybe_wait_for_rate_limit(f"get_file_content {repo_full_name} {path}")
		query = {
			"repo_full_name": repo_full_name,
			"path": path,
			"ref": ref or "",
		}
		return self.cached_query(
			"get_file_content",
			query,
			f"GET /repos/{repo_full_name}/contents/{path}",
			lambda: self._get_file_content_live(repo_full_name, path, ref),
			ttl_seconds=24 * 60 * 60,
		)

	#============================================
	def _get_file_content_live(self, repo_full_name: str, path: str, ref: str) -> dict | None:
		"""
		Fetch one file content payload from live API.
		"""
		repo_obj = self.get_repo(repo_full_name)
		self.sleep_request_jitter(f"GET /repos/{repo_full_name}/contents/{path}")
		try:
			self.record_api_call(f"GET /repos/{repo_full_name}/contents/{path}")
			if ref:
				content = repo_obj.get_contents(path, ref=ref)
			else:
				content = repo_obj.get_contents(path)
		except self._github_exception_class as error:
			status = getattr(error, "status", None)
			if status == 404:
				return None
			self.raise_from_github_error(
				error,
				f"fetching {path} for {repo_full_name}",
			)
		if isinstance(content, list):
			return None
		text = content.decoded_content.decode("utf-8", errors="replace")
		result = {
			"path": getattr(content, "path", path),
			"sha": getattr(content, "sha", ""),
			"size": getattr(content, "size", 0),
			"text": text,
		}
		return result

	#============================================
	def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
		"""
		Get decoded text for one file path.
		"""
		payload = self.get_file_content(repo_full_name, path, ref)
		if payload is None:
			return None
		return payload["text"]
