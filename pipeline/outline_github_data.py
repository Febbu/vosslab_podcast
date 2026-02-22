#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime
from datetime import timezone

from podlib import pipeline_settings


REPO_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


#============================================
def log_step(message: str) -> None:
	"""
	Print one timestamped progress line.
	"""
	now_text = datetime.now().strftime("%H:%M:%S")
	print(f"[outline_github_data {now_text}] {message}", flush=True)


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Parse GitHub JSONL data and build summary outline outputs."
	)
	parser.add_argument(
		"--input",
		default="out/github_data.jsonl",
		help="Path to input JSONL data from fetch_github_data.py.",
	)
	parser.add_argument(
		"--outline-json",
		default="out/outline.json",
		help="Path to structured outline JSON output.",
	)
	parser.add_argument(
		"--outline-txt",
		default="out/outline.txt",
		help="Path to plain-text outline output.",
	)
	parser.add_argument(
		"--repo-shards-dir",
		default="out/outline_repos",
		help="Directory for per-repo outline shard files.",
	)
	parser.add_argument(
		"--skip-repo-shards",
		action="store_true",
		help="Skip writing per-repo outline shard outputs.",
	)
	parser.add_argument(
		"--continue",
		dest="continue_mode",
		action="store_true",
		help="Reuse existing repo outline shards when available (default: enabled).",
	)
	parser.add_argument(
		"--no-continue",
		dest="continue_mode",
		action="store_false",
		help="Disable reuse of existing repo outline shards.",
	)
	parser.set_defaults(continue_mode=True)
	parser.add_argument(
		"--settings",
		default="settings.yaml",
		help="YAML settings path for LLM defaults.",
	)
	parser.add_argument(
		"--llm-transport",
		choices=["ollama", "apple", "auto"],
		default=None,
		help="local-llm-wrapper transport selection (defaults from settings.yaml).",
	)
	parser.add_argument(
		"--llm-model",
		default=None,
		help="Optional model override (defaults from settings.yaml).",
	)
	parser.add_argument(
		"--llm-max-tokens",
		type=int,
		default=None,
		help="Maximum generation tokens per call (defaults from settings.yaml).",
	)
	parser.add_argument(
		"--llm-repo-limit",
		type=int,
		default=None,
		help="Optional cap for number of repos summarized (defaults from settings.yaml).",
	)
	args = parser.parse_args()
	return args


#============================================
def parse_iso(ts: str) -> datetime:
	"""
	Parse an ISO timestamp into timezone-aware datetime.
	"""
	if not ts:
		return datetime(1970, 1, 1, tzinfo=timezone.utc)
	parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
	return parsed


#============================================
def add_local_llm_wrapper_to_path() -> None:
	"""
	Add local-llm-wrapper path to sys.path when present.
	"""
	script_dir = os.path.dirname(os.path.abspath(__file__))
	repo_root = os.path.dirname(script_dir)
	candidates = [
		os.path.join(repo_root, "local-llm-wrapper"),
		os.path.join(repo_root, "pipeline", "local-llm-wrapper"),
	]
	for wrapper_repo in candidates:
		if not os.path.isdir(wrapper_repo):
			continue
		if wrapper_repo not in sys.path:
			sys.path.insert(0, wrapper_repo)
		return


#============================================
def build_repo_context(bucket: dict) -> dict:
	"""
	Build compact repo context for LLM prompts.
	"""
	context = {
		"repo_full_name": bucket.get("repo_full_name", ""),
		"repo_name": bucket.get("repo_name", ""),
		"description": bucket.get("description", ""),
		"language": bucket.get("language", ""),
		"commit_count": bucket.get("commit_count", 0),
		"issue_count": bucket.get("issue_count", 0),
		"pull_request_count": bucket.get("pull_request_count", 0),
		"total_activity": bucket.get("total_activity", 0),
		"latest_event_time": bucket.get("latest_event_time", ""),
		"commit_messages": list(bucket.get("commit_messages", []))[:30],
		"issue_titles": list(bucket.get("issue_titles", []))[:30],
		"pull_request_titles": list(bucket.get("pull_request_titles", []))[:30],
	}
	return context


#============================================
def build_repo_llm_prompt(outline: dict, bucket: dict, rank: int, repo_total: int) -> str:
	"""
	Build one repo-specific LLM prompt.
	"""
	context = build_repo_context(bucket)
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	prompt = (
		"You are summarizing one repository from a weekly engineering dataset.\n"
		"Write a detailed outline in plain text using section headers and bullet points.\n"
		"Required sections:\n"
		"1. Executive Summary\n"
		"2. Key Workstreams\n"
		"3. Notable Commits\n"
		"4. Issues and Pull Requests\n"
		"5. Risks or Unknowns\n"
		"6. Suggested Next Actions\n"
		"Do not invent repo names or metrics. Use only provided data.\n\n"
		f"User: {outline.get('user', 'unknown')}\n"
		f"Window: {outline.get('window_start', '')} -> {outline.get('window_end', '')}\n"
		f"Repo rank: {rank} of {repo_total}\n\n"
		"Repository data JSON:\n"
		f"{context_json}\n"
	)
	return prompt


#============================================
def build_global_llm_prompt(outline: dict, repo_summaries: list[dict]) -> str:
	"""
	Build one global weekly LLM prompt from repo-level summaries.
	"""
	compact_repos = []
	for item in repo_summaries:
		compact_repos.append(
			{
				"repo_full_name": item.get("repo_full_name", ""),
				"total_activity": item.get("total_activity", 0),
				"repo_outline_excerpt": item.get("repo_outline", "")[:1500],
			}
		)
	context = {
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"totals": outline.get("totals", {}),
		"repos": compact_repos,
		"notable_commit_messages": list(outline.get("notable_commit_messages", []))[:40],
	}
	context_json = json.dumps(context, ensure_ascii=True, indent=2)
	prompt = (
		"You are creating a weekly cross-repo engineering outline.\n"
		"Write a detailed plain-text outline with these sections:\n"
		"1. Week Overview\n"
		"2. Top Repository Highlights\n"
		"3. Cross-Repo Patterns\n"
		"4. Risks and Follow-up\n"
		"5. Next Week Focus\n"
		"Do not invent counts or repository names.\n\n"
		"Context JSON:\n"
		f"{context_json}\n"
	)
	return prompt


#============================================
def create_llm_client(
	transport_name: str,
	model_override: str,
) -> object:
	"""
	Create local-llm-wrapper client for outline summarization.
	"""
	add_local_llm_wrapper_to_path()
	import local_llm_wrapper.llm as llm

	model_choice = llm.choose_model(model_override or None)
	transports = []
	if transport_name == "ollama":
		transports.append(llm.OllamaTransport(model=model_choice))
	elif transport_name == "apple":
		transports.append(llm.AppleTransport())
	elif transport_name == "auto":
		transports.append(llm.AppleTransport())
		transports.append(llm.OllamaTransport(model=model_choice))
	else:
		raise RuntimeError(f"Unsupported llm transport: {transport_name}")
	client = llm.LLMClient(transports=transports, quiet=True)
	return client


#============================================
def load_cached_repo_outline_map(repo_shards_dir: str, outline: dict) -> dict[str, str]:
	"""
	Load repo outline cache from shard JSON files when metadata matches.
	"""
	shards_path = os.path.abspath(repo_shards_dir)
	if not os.path.isdir(shards_path):
		return {}

	target_user = (outline.get("user") or "").strip()
	target_window_start = (outline.get("window_start") or "").strip()
	target_window_end = (outline.get("window_end") or "").strip()
	cache: dict[str, str] = {}

	candidate_paths: list[str] = []
	manifest_path = os.path.join(shards_path, "index.json")
	if os.path.isfile(manifest_path):
		try:
			with open(manifest_path, "r", encoding="utf-8") as handle:
				manifest = json.load(handle)
			entries = manifest.get("repo_shards") or []
			for entry in entries:
				if not isinstance(entry, dict):
					continue
				json_path = str(entry.get("json_path") or "").strip()
				if not json_path:
					continue
				if not os.path.isabs(json_path):
					json_path = os.path.join(shards_path, json_path)
				if os.path.isfile(json_path):
					candidate_paths.append(os.path.abspath(json_path))
		except Exception:
			candidate_paths = []
	if not candidate_paths:
		fallback_paths = glob.glob(os.path.join(shards_path, "*.json"))
		for json_path in fallback_paths:
			if os.path.basename(json_path) == "index.json":
				continue
			candidate_paths.append(os.path.abspath(json_path))

	for json_path in candidate_paths:
		try:
			with open(json_path, "r", encoding="utf-8") as handle:
				shard = json.load(handle)
		except Exception:
			continue
		if not isinstance(shard, dict):
			continue
		shard_user = (shard.get("user") or "").strip()
		shard_window_start = (shard.get("window_start") or "").strip()
		shard_window_end = (shard.get("window_end") or "").strip()
		if target_user and (shard_user != target_user):
			continue
		if target_window_start and (shard_window_start != target_window_start):
			continue
		if target_window_end and (shard_window_end != target_window_end):
			continue
		bucket = shard.get("repo_activity")
		if not isinstance(bucket, dict):
			continue
		repo_full_name = str(bucket.get("repo_full_name") or "").strip()
		if not repo_full_name:
			continue
		repo_outline = str(bucket.get("llm_repo_outline") or "").strip()
		if not repo_outline:
			continue
		cache[repo_full_name] = repo_outline
	return cache


#============================================
def summarize_outline_with_llm(
	outline: dict,
	*,
	transport_name: str,
	model_override: str,
	max_tokens: int,
	repo_limit: int,
	repo_shards_dir: str = "out/outline_repos",
	continue_mode: bool = True,
) -> dict:
	"""
	Generate repo and global summaries with local-llm-wrapper.
	"""
	log_step(
		f"Initializing LLM summarization with transport={transport_name}, "
		+ f"model={model_override or 'auto'}, max_tokens={max_tokens}, "
		+ f"repo_limit={repo_limit}, continue_mode={continue_mode}"
	)
	repos = outline.get("repo_activity", [])
	repo_total = len(repos)
	selected_repos = repos
	if repo_limit > 0:
		selected_repos = repos[:repo_limit]
	log_step(f"Summarizing {len(selected_repos)} repo(s) out of {repo_total} total.")
	cache_hits = 0
	cached_repo_outlines: dict[str, str] = {}
	if continue_mode:
		cached_repo_outlines = load_cached_repo_outline_map(repo_shards_dir, outline)
		log_step(
			f"Loaded {len(cached_repo_outlines)} cached repo outline(s) from "
			+ os.path.abspath(repo_shards_dir)
		)
	else:
		log_step("Continue mode disabled; regenerating all repo outlines.")

	repo_summaries = []
	client = None
	for rank, bucket in enumerate(selected_repos, start=1):
		repo_name = bucket.get("repo_full_name", "")
		repo_outline = cached_repo_outlines.get(repo_name, "")
		if repo_outline:
			cache_hits += 1
			log_step(f"Reusing cached repo outline {rank}/{len(selected_repos)}: {repo_name}")
		else:
			if client is None:
				client = create_llm_client(transport_name, model_override)
			log_step(f"Generating repo outline {rank}/{len(selected_repos)}: {repo_name}")
			prompt = build_repo_llm_prompt(outline, bucket, rank, repo_total)
			repo_outline = client.generate(
				prompt=prompt,
				purpose="weekly repo outline",
				max_tokens=max_tokens,
			).strip()
		bucket["llm_repo_outline"] = repo_outline
		log_step(f"Completed repo outline for {repo_name}; chars={len(repo_outline)}")
		repo_summaries.append(
			{
				"repo_full_name": bucket.get("repo_full_name", ""),
				"total_activity": bucket.get("total_activity", 0),
				"repo_outline": repo_outline,
			}
		)

	log_step("Generating global weekly outline from repo summaries.")
	if client is None:
		client = create_llm_client(transport_name, model_override)
	global_prompt = build_global_llm_prompt(outline, repo_summaries)
	global_outline = client.generate(
		prompt=global_prompt,
		purpose="weekly global outline",
		max_tokens=max_tokens,
	).strip()
	outline["llm_global_outline"] = global_outline
	outline["llm_repo_summaries_count"] = len(selected_repos)
	outline["llm_cached_repo_outline_count"] = cache_hits
	outline["llm_generated_repo_outline_count"] = len(selected_repos) - cache_hits
	outline["llm_transport"] = transport_name
	outline["llm_model"] = model_override or "auto"
	log_step(f"Completed global outline; chars={len(global_outline)}")
	return outline


#============================================
def ensure_repo_bucket(repo_map: dict[str, dict], repo_full_name: str, repo_name: str) -> dict:
	"""
	Create or return a repo aggregation bucket.
	"""
	if repo_full_name not in repo_map:
		repo_map[repo_full_name] = {
			"repo_full_name": repo_full_name,
			"repo_name": repo_name or repo_full_name,
			"html_url": "",
			"description": "",
			"language": "",
			"commit_count": 0,
			"issue_count": 0,
			"pull_request_count": 0,
			"commit_messages": [],
			"issue_titles": [],
			"pull_request_titles": [],
			"latest_event_time": "",
		}
	return repo_map[repo_full_name]


#============================================
def update_latest_event(bucket: dict, event_time: str) -> None:
	"""
	Update latest event marker for one repo bucket.
	"""
	if not event_time:
		return
	current = bucket.get("latest_event_time", "")
	if not current:
		bucket["latest_event_time"] = event_time
		return
	if parse_iso(event_time) > parse_iso(current):
		bucket["latest_event_time"] = event_time


#============================================
def parse_jsonl_to_outline(input_path: str) -> dict:
	"""
	Parse JSONL records and aggregate summary outline data.
	"""
	if not os.path.isfile(input_path):
		raise FileNotFoundError(f"Missing JSONL input: {input_path}")

	repo_map: dict[str, dict] = {}
	user = ""
	window_start = ""
	window_end = ""
	run_metadata_count = 0
	run_summary_count = 0
	totals = {
		"repo_records": 0,
		"commit_records": 0,
		"issue_records": 0,
		"pull_request_records": 0,
	}

	with open(input_path, "r", encoding="utf-8") as handle:
		for raw_line in handle:
			line = raw_line.strip()
			if not line:
				continue
			record = json.loads(line)
			record_type = record.get("record_type", "")
			if record.get("user"):
				user = record["user"]
			if record.get("window_start"):
				window_start = record["window_start"]
			if record.get("window_end"):
				window_end = record["window_end"]

			if record_type == "run_metadata":
				run_metadata_count += 1
				continue
			if record_type == "run_summary":
				run_summary_count += 1
				continue

			repo_full_name = record.get("repo_full_name") or ""
			repo_name = record.get("repo_name") or repo_full_name
			if not repo_full_name:
				continue
			bucket = ensure_repo_bucket(repo_map, repo_full_name, repo_name)
			update_latest_event(bucket, record.get("event_time", ""))

			if record_type == "repo":
				totals["repo_records"] += 1
				data = record.get("data") or {}
				bucket["repo_name"] = data.get("name") or bucket["repo_name"]
				bucket["html_url"] = data.get("html_url") or bucket["html_url"]
				bucket["description"] = data.get("description") or bucket["description"]
				bucket["language"] = data.get("language") or bucket["language"]
				continue

			if record_type == "commit":
				totals["commit_records"] += 1
				bucket["commit_count"] += 1
				message = record.get("message") or ""
				first_line = message.splitlines()[0].strip() if message else ""
				if first_line:
					bucket["commit_messages"].append(first_line)
				continue

			if record_type == "issue":
				totals["issue_records"] += 1
				bucket["issue_count"] += 1
				title = (record.get("title") or "").strip()
				if title:
					bucket["issue_titles"].append(title)
				continue

			if record_type == "pull_request":
				totals["pull_request_records"] += 1
				bucket["pull_request_count"] += 1
				title = (record.get("title") or "").strip()
				if title:
					bucket["pull_request_titles"].append(title)
				continue

	for repo_full_name in repo_map:
		bucket = repo_map[repo_full_name]
		bucket["total_activity"] = (
			bucket["commit_count"]
			+ bucket["issue_count"]
			+ bucket["pull_request_count"]
		)

	repos = list(repo_map.values())
	repos.sort(
		key=lambda item: (item["total_activity"], item["commit_count"], item["repo_full_name"]),
		reverse=True,
	)

	notable_commit_messages = []
	for bucket in repos:
		for message in bucket["commit_messages"]:
			if message not in notable_commit_messages:
				notable_commit_messages.append(message)
			if len(notable_commit_messages) >= 30:
				break
		if len(notable_commit_messages) >= 30:
			break

	outline = {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"source_jsonl": os.path.abspath(input_path),
		"user": user or "unknown",
		"window_start": window_start,
		"window_end": window_end,
		"totals": {
			"repos": len(repos),
			"repo_records": totals["repo_records"],
			"commit_records": totals["commit_records"],
			"issue_records": totals["issue_records"],
			"pull_request_records": totals["pull_request_records"],
			"run_metadata_records": run_metadata_count,
			"run_summary_records": run_summary_count,
		},
		"repo_activity": repos,
		"notable_commit_messages": notable_commit_messages,
	}
	return outline


#============================================
def render_outline_text(outline: dict) -> str:
	"""
	Render an unlimited-length plain-text outline.
	"""
	user = outline.get("user", "unknown")
	window_start = outline.get("window_start", "")
	window_end = outline.get("window_end", "")
	totals = outline.get("totals", {})
	repos = outline.get("repo_activity", [])

	lines = []
	lines.append("GitHub Weekly Outline")
	lines.append(f"User: {user}")
	lines.append(f"Window: {window_start} -> {window_end}")
	lines.append("")
	lines.append("Totals")
	lines.append(f"- Repos with activity: {totals.get('repos', 0)}")
	lines.append(f"- Repo records: {totals.get('repo_records', 0)}")
	lines.append(f"- Commit records: {totals.get('commit_records', 0)}")
	lines.append(f"- Issue records: {totals.get('issue_records', 0)}")
	lines.append(f"- Pull request records: {totals.get('pull_request_records', 0)}")
	lines.append("")
	lines.append("Repository Breakdown")

	for index, bucket in enumerate(repos, 1):
		lines.append(
			f"{index}. {bucket.get('repo_full_name', '')} "
			f"(activity={bucket.get('total_activity', 0)})"
		)
		lines.append(f"   - Commits: {bucket.get('commit_count', 0)}")
		lines.append(f"   - Issues: {bucket.get('issue_count', 0)}")
		lines.append(f"   - Pull requests: {bucket.get('pull_request_count', 0)}")
		description = (bucket.get("description") or "").strip()
		if description:
			lines.append(f"   - Description: {description}")
		language = (bucket.get("language") or "").strip()
		if language:
			lines.append(f"   - Language: {language}")
		if bucket.get("commit_messages"):
			lines.append("   - Commit messages:")
			for commit_message in bucket["commit_messages"]:
				lines.append(f"     * {commit_message}")
		if bucket.get("issue_titles"):
			lines.append("   - Issues:")
			for title in bucket["issue_titles"]:
				lines.append(f"     * {title}")
		if bucket.get("pull_request_titles"):
			lines.append("   - Pull requests:")
			for title in bucket["pull_request_titles"]:
				lines.append(f"     * {title}")
		lines.append("")

	lines.append("Cross-Repo Commit Highlights")
	for message in outline.get("notable_commit_messages", []):
		lines.append(f"- {message}")
	lines.append("")
	global_outline = (outline.get("llm_global_outline") or "").strip()
	if global_outline:
		lines.append("LLM Weekly Outline")
		lines.append(global_outline)

	rendered = "\n".join(lines).strip() + "\n"
	return rendered


#============================================
def sanitize_repo_slug(repo_full_name: str) -> str:
	"""
	Build a filesystem-safe repo slug for shard filenames.
	"""
	text = repo_full_name.strip().lower().replace("/", "__")
	text = REPO_SLUG_RE.sub("_", text)
	text = text.strip("._-")
	if not text:
		return "repo"
	return text


#============================================
def render_repo_outline_text(outline: dict, bucket: dict, rank: int, repo_total: int) -> str:
	"""
	Render one repo-scoped outline text shard.
	"""
	lines = []
	lines.append("GitHub Repo Outline")
	lines.append(f"User: {outline.get('user', 'unknown')}")
	lines.append(f"Window: {outline.get('window_start', '')} -> {outline.get('window_end', '')}")
	lines.append(f"Rank: {rank} of {repo_total}")
	lines.append(f"Repo: {bucket.get('repo_full_name', '')}")
	lines.append(f"Total activity: {bucket.get('total_activity', 0)}")
	lines.append(f"Commits: {bucket.get('commit_count', 0)}")
	lines.append(f"Issues: {bucket.get('issue_count', 0)}")
	lines.append(f"Pull requests: {bucket.get('pull_request_count', 0)}")
	description = (bucket.get("description") or "").strip()
	if description:
		lines.append(f"Description: {description}")
	language = (bucket.get("language") or "").strip()
	if language:
		lines.append(f"Language: {language}")
	lines.append("")
	if bucket.get("commit_messages"):
		lines.append("Commit messages:")
		for message in bucket["commit_messages"]:
			lines.append(f"- {message}")
		lines.append("")
	if bucket.get("issue_titles"):
		lines.append("Issue titles:")
		for title in bucket["issue_titles"]:
			lines.append(f"- {title}")
		lines.append("")
	if bucket.get("pull_request_titles"):
		lines.append("Pull request titles:")
		for title in bucket["pull_request_titles"]:
			lines.append(f"- {title}")
		lines.append("")
	repo_outline = (bucket.get("llm_repo_outline") or "").strip()
	if repo_outline:
		lines.append("LLM Repo Outline")
		lines.append(repo_outline)
		lines.append("")
	rendered = "\n".join(lines).strip() + "\n"
	return rendered


#============================================
def write_repo_outline_shards(outline: dict, repo_shards_dir: str) -> str:
	"""
	Write one JSON and text shard per repo plus an index manifest.
	"""
	repos = outline.get("repo_activity", [])
	shards_path = os.path.abspath(repo_shards_dir)
	os.makedirs(shards_path, exist_ok=True)

	manifest_items = []
	repo_total = len(repos)
	for index, bucket in enumerate(repos, start=1):
		repo_full_name = bucket.get("repo_full_name", "")
		repo_slug = sanitize_repo_slug(repo_full_name)
		base_name = f"{index:03d}_{repo_slug}"
		repo_json_path = os.path.join(shards_path, base_name + ".json")
		repo_txt_path = os.path.join(shards_path, base_name + ".txt")
		repo_outline = {
			"generated_at": outline.get("generated_at", ""),
			"user": outline.get("user", "unknown"),
			"window_start": outline.get("window_start", ""),
			"window_end": outline.get("window_end", ""),
			"repo_rank": index,
			"repo_total": repo_total,
			"repo_activity": bucket,
		}
		with open(repo_json_path, "w", encoding="utf-8") as json_handle:
			json.dump(repo_outline, json_handle, indent=2)
			json_handle.write("\n")
		repo_text = render_repo_outline_text(outline, bucket, index, repo_total)
		with open(repo_txt_path, "w", encoding="utf-8") as txt_handle:
			txt_handle.write(repo_text)
		manifest_items.append(
			{
				"repo_full_name": repo_full_name,
				"repo_name": bucket.get("repo_name", ""),
				"repo_rank": index,
				"total_activity": bucket.get("total_activity", 0),
				"json_path": repo_json_path,
				"txt_path": repo_txt_path,
			}
		)

	manifest = {
		"generated_at": outline.get("generated_at", ""),
		"user": outline.get("user", "unknown"),
		"window_start": outline.get("window_start", ""),
		"window_end": outline.get("window_end", ""),
		"repo_count": repo_total,
		"repo_shards": manifest_items,
	}
	manifest_path = os.path.join(shards_path, "index.json")
	with open(manifest_path, "w", encoding="utf-8") as handle:
		json.dump(manifest, handle, indent=2)
		handle.write("\n")
	return manifest_path


#============================================
def write_outline_outputs(
	outline: dict,
	outline_json_path: str,
	outline_txt_path: str,
	repo_shards_dir: str,
	skip_repo_shards: bool,
) -> None:
	"""
	Write outline outputs to JSON and text files.
	"""
	json_path = os.path.abspath(outline_json_path)
	txt_path = os.path.abspath(outline_txt_path)
	os.makedirs(os.path.dirname(json_path), exist_ok=True)
	os.makedirs(os.path.dirname(txt_path), exist_ok=True)

	with open(json_path, "w", encoding="utf-8") as json_handle:
		json.dump(outline, json_handle, indent=2)
		json_handle.write("\n")

	outline_text = render_outline_text(outline)
	with open(txt_path, "w", encoding="utf-8") as txt_handle:
		txt_handle.write(outline_text)

	log_step(f"Wrote outline JSON: {json_path}")
	log_step(f"Wrote outline text: {txt_path}")
	if skip_repo_shards:
		log_step("Skipping repo shard output by request.")
		return

	manifest_path = write_repo_outline_shards(outline, repo_shards_dir)
	log_step(f"Wrote repo shard manifest: {manifest_path}")


#============================================
def main() -> None:
	"""
	Run outline generation from JSONL input.
	"""
	args = parse_args()
	settings, settings_path = pipeline_settings.load_settings(args.settings)
	default_transport = pipeline_settings.get_enabled_llm_transport(settings)
	default_model = pipeline_settings.get_llm_provider_model(settings, default_transport)
	default_max_tokens = pipeline_settings.get_setting_int(settings, ["llm", "max_tokens"], 1200)
	default_repo_limit = pipeline_settings.get_setting_int(settings, ["llm", "repo_limit"], 0)

	transport_name = args.llm_transport or default_transport
	if transport_name not in {"ollama", "apple", "auto"}:
		raise RuntimeError(f"Unsupported llm transport in settings: {transport_name}")
	model_override = default_model
	if args.llm_model is not None:
		model_override = args.llm_model.strip()
	max_tokens = default_max_tokens if args.llm_max_tokens is None else args.llm_max_tokens
	repo_limit = default_repo_limit if args.llm_repo_limit is None else args.llm_repo_limit
	if max_tokens < 1:
		raise RuntimeError("llm max tokens must be >= 1")
	if repo_limit < 0:
		raise RuntimeError("llm repo limit must be >= 0")

	log_step(f"Using settings file: {settings_path}")
	log_step(
		"Using LLM settings: "
		+ f"transport={transport_name}, model={model_override or 'auto'}, "
		+ f"max_tokens={max_tokens}, repo_limit={repo_limit}"
	)
	log_step(f"Parsing input JSONL: {os.path.abspath(args.input)}")
	outline = parse_jsonl_to_outline(args.input)
	log_step(
		f"Parsed outline totals: repos={outline.get('totals', {}).get('repos', 0)}, "
		+ f"commits={outline.get('totals', {}).get('commit_records', 0)}, "
		+ f"issues={outline.get('totals', {}).get('issue_records', 0)}, "
		+ f"prs={outline.get('totals', {}).get('pull_request_records', 0)}"
	)
	outline = summarize_outline_with_llm(
		outline,
		transport_name=transport_name,
		model_override=model_override,
		max_tokens=max_tokens,
		repo_limit=repo_limit,
		repo_shards_dir=args.repo_shards_dir,
		continue_mode=args.continue_mode,
	)
	write_outline_outputs(
		outline,
		args.outline_json,
		args.outline_txt,
		args.repo_shards_dir,
		args.skip_repo_shards,
	)
	log_step("Outline stage complete.")


if __name__ == "__main__":
	main()
