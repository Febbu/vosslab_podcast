import os
import sys
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace

import git_file_utils


REPO_ROOT = git_file_utils.get_repo_root()
PIPELINE_DIR = os.path.join(REPO_ROOT, "pipeline")
if PIPELINE_DIR not in sys.path:
	sys.path.insert(0, PIPELINE_DIR)

from podlib import github_client


#============================================
def make_stub_client(overview_object):
	"""
	Build GitHubClient instance with mocked get_rate_limit response.
	"""
	client = github_client.GitHubClient.__new__(github_client.GitHubClient)
	client.log_fn = None
	client._rate_check_count = 0
	client._low_remaining_threshold = 5
	client.client = SimpleNamespace(get_rate_limit=lambda: overview_object)
	return client


#============================================
def test_core_rate_limit_snapshot_from_core_attribute() -> None:
	"""
	Rate limit should parse from overview.core shape.
	"""
	reset_time = datetime(2026, 2, 22, 3, 30, 0, tzinfo=timezone.utc)
	overview = SimpleNamespace(
		core=SimpleNamespace(
			remaining=42,
			reset=reset_time,
		)
	)
	client = make_stub_client(overview)
	remaining, parsed_reset = client.get_core_rate_limit_snapshot()
	assert remaining == 42
	assert parsed_reset == reset_time


#============================================
def test_core_rate_limit_snapshot_from_resources_attribute() -> None:
	"""
	Rate limit should parse from overview.resources.core shape.
	"""
	overview = SimpleNamespace(
		resources=SimpleNamespace(
			core=SimpleNamespace(
				remaining=9,
				reset="2026-02-22T03:35:00+00:00",
			)
		)
	)
	client = make_stub_client(overview)
	remaining, parsed_reset = client.get_core_rate_limit_snapshot()
	assert remaining == 9
	assert parsed_reset.isoformat() == "2026-02-22T03:35:00+00:00"


#============================================
def test_core_rate_limit_snapshot_from_resources_dict() -> None:
	"""
	Rate limit should parse from overview.resources['core'] shape.
	"""
	overview = SimpleNamespace(
		resources={
			"core": SimpleNamespace(
				remaining=3,
				reset=1761110400,
			)
		}
	)
	client = make_stub_client(overview)
	remaining, parsed_reset = client.get_core_rate_limit_snapshot()
	assert remaining == 3
	assert parsed_reset.tzinfo is not None


#============================================
def test_maybe_wait_for_rate_limit_handles_unknown_shape() -> None:
	"""
	Unknown rate-limit shape should not crash wait checks.
	"""
	client = make_stub_client(SimpleNamespace(resources={}))
	client.maybe_wait_for_rate_limit("unit-test", force=True)
