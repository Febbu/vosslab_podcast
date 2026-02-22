import random
import time
from datetime import datetime
from datetime import timezone


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
		self._retry_wait_seconds = 10
		self._retry_attempts_on_403 = 1
		try:
			from github import Github
			from github.GithubException import GithubException
		except ModuleNotFoundError as error:
			raise RuntimeError(
				"Missing dependency: PyGithub. Install it with pip install PyGithub."
			) from error
		self._github_exception_class = GithubException
		if token:
			self.client = Github(token)
		else:
			self.client = Github()

	#============================================
	def log(self, message: str) -> None:
		"""
		Emit one log line when logger is configured.
		"""
		if self.log_fn is not None:
			self.log_fn(message)

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
		Run one API call with jitter and one retry on 403.
		"""
		attempt = 0
		while True:
			self.sleep_request_jitter(context)
			try:
				return call_fn()
			except self._github_exception_class as error:
				status = getattr(error, "status", None)
				if (status == 403) and (attempt < self._retry_attempts_on_403):
					attempt += 1
					wait_seconds = self._retry_wait_seconds
					self.log(
						f"Request {context} hit 403; sleeping {wait_seconds}s before retry "
						+ f"({attempt}/{self._retry_attempts_on_403})."
					)
					time.sleep(wait_seconds)
					continue
				self.raise_from_github_error(error, context)

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
		return self.call_with_retry(
			f"GET /users/{user}/repos",
			lambda: self.client.get_user(user).get_repos(
				type="owner",
				sort="updated",
				direction="desc",
			),
		)

	#============================================
	def list_commits(self, repo_obj, since: datetime, until: datetime):
		"""
		List repository commits inside time window.
		"""
		self.maybe_wait_for_rate_limit(f"list_commits {repo_obj.full_name}")
		return self.call_with_retry(
			f"GET /repos/{repo_obj.full_name}/commits",
			lambda: repo_obj.get_commits(since=since, until=until),
		)

	#============================================
	def list_issues(self, repo_obj, since: datetime):
		"""
		List repository issues and pull requests updated since window start.
		"""
		self.maybe_wait_for_rate_limit(f"list_issues {repo_obj.full_name}")
		return self.call_with_retry(
			f"GET /repos/{repo_obj.full_name}/issues",
			lambda: repo_obj.get_issues(
				state="all",
				since=since,
				sort="updated",
				direction="desc",
			),
		)

	#============================================
	def get_file_content(self, repo_obj, path: str, ref: str) -> dict | None:
		"""
		Get one file content payload with metadata.
		"""
		self.maybe_wait_for_rate_limit(f"get_file_content {repo_obj.full_name} {path}")
		attempt = 0
		while True:
			self.sleep_request_jitter(f"GET /repos/{repo_obj.full_name}/contents/{path}")
			try:
				if ref:
					content = repo_obj.get_contents(path, ref=ref)
				else:
					content = repo_obj.get_contents(path)
				break
			except self._github_exception_class as error:
				status = getattr(error, "status", None)
				if status == 404:
					return None
				if (status == 403) and (attempt < self._retry_attempts_on_403):
					attempt += 1
					wait_seconds = self._retry_wait_seconds
					self.log(
						f"Request GET /repos/{repo_obj.full_name}/contents/{path} hit 403; "
						+ f"sleeping {wait_seconds}s before retry "
						+ f"({attempt}/{self._retry_attempts_on_403})."
					)
					time.sleep(wait_seconds)
					continue
				self.raise_from_github_error(
					error,
					f"fetching {path} for {repo_obj.full_name}",
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
	def get_file_text(self, repo_obj, path: str, ref: str) -> str | None:
		"""
		Get decoded text for one file path.
		"""
		payload = self.get_file_content(repo_obj, path, ref)
		if payload is None:
			return None
		return payload["text"]
