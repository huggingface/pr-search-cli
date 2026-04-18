from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pr_search_cli.cli import (
    BASE_URL_ENV_VAR,
    _infer_base_url_from_repo,
    _resolve_base_url,
    _space_slug,
)

RoutePayload = object | tuple[int, object]
TEST_ENV = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}


def test_module_help_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pr_search_cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=TEST_ENV,
    )

    assert result.returncode == 0
    assert "usage: pr-search" in result.stdout
    assert "code" in result.stdout
    assert "issues" in result.stdout
    assert "contributors" in result.stdout


def test_base_url_is_inferred_from_repo_by_convention() -> None:
    assert _infer_base_url_from_repo("huggingface/transformers") == (
        "https://evalstate-transformers-pr-api.hf.space"
    )
    assert _infer_base_url_from_repo("huggingface/diffusers") == (
        "https://evalstate-diffusers-pr-api.hf.space"
    )
    assert _infer_base_url_from_repo("openclaw/openclaw") == (
        "https://evalstate-openclaw-pr-api.hf.space"
    )


def test_base_url_resolution_prefers_explicit_url() -> None:
    assert _resolve_base_url("https://example.test", "huggingface/transformers") == (
        "https://example.test"
    )


def test_base_url_resolution_uses_env_var(monkeypatch) -> None:
    monkeypatch.setenv(BASE_URL_ENV_VAR, "https://env.example.test")
    assert _resolve_base_url(None, "huggingface/transformers") == "https://env.example.test"


def test_space_slug_normalizes_repo_names() -> None:
    assert _space_slug("my_repo") == "my-repo"
    assert _space_slug("Repo.Name") == "repo-name"


def test_group_without_subcommand_prints_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pr_search_cli", "issues"],
        capture_output=True,
        text=True,
        check=False,
        env=TEST_ENV,
    )

    assert result.returncode == 0
    assert "usage: pr-search issues" in result.stdout
    assert "contains-pr" in result.stdout


def test_status_and_code_similar_json() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/status": {
            "id": "run-1",
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "source_type": "hf_dataset_repo",
            "finished_at": "2026-04-16T12:00:00Z",
            "row_counts": {
                "documents": 100,
                "features": 100,
                "neighbors": 50,
                "clusters": 7,
                "cluster_candidates": 12,
            },
            "surfaces": {
                "issues": {
                    "available": True,
                    "variant_used": "hybrid",
                    "llm_enrichment": True,
                    "generated_at": "2026-04-16T12:10:00Z",
                    "cluster_count": 3,
                    "duplicate_pr_count": 2,
                    "available_variants": ["hybrid"],
                },
                "contributors": {
                    "available": True,
                    "generated_at": "2026-04-16T12:20:00Z",
                    "contributor_count": 5,
                },
            },
        },
        "/v1/repos/openclaw/openclaw/pulls/123/similar?mode=auto&limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "similar_count": 1,
            "query": {
                "pr_number": 123,
                "mode_requested": "auto",
                "mode_used": "indexed",
                "source": "active_index",
            },
            "pr": {"pr_number": 123, "title": "Fix CI"},
            "similar_prs": [
                {
                    "neighbor_pr_number": 99,
                    "neighbor_title": "Fix CI cache",
                    "similarity": 0.92,
                    "content_similarity": 0.91,
                    "size_similarity": 0.95,
                    "breadth_similarity": 0.88,
                    "concentration_similarity": 0.90,
                    "shared_filenames": ["src/ci.py"],
                    "shared_directories": [],
                    "cluster_ids": ["pr-scope-99-2"],
                }
            ],
        },
    }
    with _json_server(routes) as base_url:
        status = subprocess.run(
            [sys.executable, "-m", "pr_search_cli", "--base-url", base_url, "status"],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        similar = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--format",
                "json",
                "code",
                "similar",
                "123",
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert status.returncode == 0
    assert "SURFACES" in status.stdout
    assert "contributors=5" in status.stdout
    payload = json.loads(similar.stdout)
    assert payload["similar_prs"][0]["neighbor_pr_number"] == 99
    assert payload["similar_prs"][0]["neighbor_title"] == "Fix CI cache"


def test_issue_commands_text_and_ids() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/issues/status?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "available_variants": ["hybrid"],
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "counts": {"meta_bugs": 1, "duplicate_issues": 0, "duplicate_prs": 1},
        },
        "/v1/repos/openclaw/openclaw/issues/clusters?variant=auto&limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "cluster_count": 1,
            "clusters": [
                {
                    "rank": 1,
                    "cluster_id": "issue-cluster-100-2",
                    "title": "Tokenizer issue",
                    "summary": "Tokenizer issue cluster",
                    "status": "open",
                    "confidence": 0.93,
                    "canonical_issue_number": 100,
                    "canonical_pr_number": 123,
                    "issue_count": 1,
                    "pr_count": 2,
                }
            ],
        },
        "/v1/repos/openclaw/openclaw/issues/clusters/issue-cluster-100-2?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "cluster_id": "issue-cluster-100-2",
            "found": True,
            "cluster": {
                "cluster_id": "issue-cluster-100-2",
                "title": "Tokenizer issue",
                "summary": "Tokenizer issue cluster",
                "status": "open",
                "confidence": 0.93,
                "canonical_issue_number": 100,
                "canonical_pr_number": 123,
                "evidence_types": ["closing_reference"],
            },
            "issues": [
                {
                    "number": 100,
                    "state": "open",
                    "author_login": "alice",
                    "title": "Tokenizer issue",
                }
            ],
            "pull_requests": [
                {
                    "number": 123,
                    "role": "canonical",
                    "author_login": "alice",
                    "state": "open",
                    "merged": False,
                    "draft": False,
                    "title": "Fix tokenizer",
                },
                {
                    "number": 124,
                    "role": "member",
                    "author_login": "bob",
                    "state": "open",
                    "merged": False,
                    "draft": False,
                    "title": "Fix tokenizer cache",
                },
            ],
        },
        "/v1/repos/openclaw/openclaw/issues/pulls/123?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "pr_number": 123,
            "found": True,
            "cluster_count": 1,
            "clusters": [
                {
                    "cluster_id": "issue-cluster-100-2",
                    "membership_role": "canonical",
                    "canonical_issue_number": 100,
                    "canonical_pr_number": 123,
                    "status": "open",
                    "confidence": 0.93,
                    "title": "Tokenizer issue",
                }
            ],
        },
        "/v1/repos/openclaw/openclaw/issues/pulls/123/membership?variant=auto&cluster_id=issue-cluster-100-2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "pr_number": 123,
            "found": True,
            "cluster_count": 1,
            "clusters": [{"cluster_id": "issue-cluster-100-2", "membership_role": "canonical"}],
            "cluster_id": "issue-cluster-100-2",
            "matched": True,
            "matching_cluster_ids": ["issue-cluster-100-2"],
            "membership": {"cluster_id": "issue-cluster-100-2", "membership_role": "canonical"},
        },
        "/v1/repos/openclaw/openclaw/issues/duplicate-prs?variant=auto&limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "duplicate_pr_count": 1,
            "duplicate_prs": [
                {
                    "rank": 1,
                    "cluster_id": "issue-cluster-100-2",
                    "target_issue_number": 100,
                    "canonical_pr_number": 123,
                    "duplicate_pr_numbers": [124],
                    "reason": "Same fix path.",
                }
            ],
        },
        "/v1/repos/openclaw/openclaw/issues/best?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "best_issue": {
                "issue_number": 100,
                "title": "Tokenizer issue",
                "cluster_id": "issue-cluster-100-2",
                "score": 0.91,
                "reason": "Best issue.",
            },
            "best_pr": {
                "pr_number": 123,
                "title": "Fix tokenizer",
                "cluster_id": "issue-cluster-100-2",
                "score": 0.92,
                "reason": "Best PR.",
            },
        },
    }
    with _json_server(routes) as base_url:
        list_ids = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--format",
                "ids",
                "issues",
                "list",
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        show = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "issues",
                "show",
                "issue-cluster-100-2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        membership = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "issues",
                "contains-pr",
                "123",
                "issue-cluster-100-2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert list_ids.returncode == 0
    assert list_ids.stdout.strip() == "issue-cluster-100-2"
    assert show.returncode == 0
    assert "PULL REQUESTS" in show.stdout
    assert "Tokenizer issue" in show.stdout
    assert membership.returncode == 0
    assert "matched" in membership.stdout
    assert "yes" in membership.stdout


def test_contributor_commands_text_jsonl_and_legacy_alias() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/contributors/status": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "available": True,
            "generated_at": "2026-04-16T12:30:00Z",
            "window_days": 42,
            "contributor_count": 1,
        },
        "/v1/repos/openclaw/openclaw/contributors?limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "available": True,
            "generated_at": "2026-04-16T12:30:00Z",
            "contributor_count": 1,
            "contributors": [
                {
                    "rank": 1,
                    "author_login": "alice",
                    "repo_association": "CONTRIBUTOR",
                    "snapshot_pr_count": 1,
                    "snapshot_issue_count": 0,
                    "first_seen_in_snapshot": True,
                    "automation_risk_signal": "low",
                    "heuristic_note": "Looks normal.",
                }
            ],
        },
        "/v1/repos/openclaw/openclaw/contributors/alice": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "available": True,
            "generated_at": "2026-04-16T12:30:00Z",
            "author_login": "alice",
            "found": True,
            "summary": {
                "author_login": "alice",
                "name": "Alice",
                "profile_url": "https://github.com/alice",
                "repo_association": "CONTRIBUTOR",
                "first_seen_in_snapshot": True,
                "new_to_repo": True,
                "snapshot_pr_count": 1,
                "snapshot_issue_count": 0,
                "follow_through_score": 3,
                "breadth_score": 2,
                "automation_risk_signal": "low",
                "heuristic_note": "Looks normal.",
                "account_age_days": 120,
                "public_pr_count_42d": 5,
                "public_repo_count_42d": 2,
            },
            "risk": {
                "automation_risk_signal": "low",
                "heuristic_note": "Looks normal.",
                "follow_through_score": 3,
                "breadth_score": 2,
                "account_age_days": 120,
                "public_pr_count_42d": 5,
                "public_repo_count_42d": 2,
                "report_reason": "new contributor",
            },
            "contributor": {
                "examples": {
                    "pull_requests": [
                        {
                            "number": 123,
                            "title": "Fix tokenizer",
                            "state": "open",
                            "merged": False,
                            "draft": False,
                        }
                    ],
                    "issues": [],
                }
            },
        },
        "/v1/repos/openclaw/openclaw/contributors/alice/risk": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "available": True,
            "generated_at": "2026-04-16T12:30:00Z",
            "author_login": "alice",
            "found": True,
            "risk_available": True,
            "risk": {
                "automation_risk_signal": "low",
                "heuristic_note": "Looks normal.",
                "follow_through_score": 3,
                "breadth_score": 2,
                "account_age_days": 120,
                "public_pr_count_42d": 5,
                "public_repo_count_42d": 2,
                "report_reason": "new contributor",
            },
        },
        "/v1/repos/openclaw/openclaw/issues/clusters?variant=auto&limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "available": True,
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "cluster_count": 1,
            "clusters": [{"cluster_id": "issue-cluster-100-2"}],
        },
    }
    with _json_server(routes) as base_url:
        contributor_list = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--format",
                "jsonl",
                "contributors",
                "list",
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        contributor_show = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "contributors",
                "show",
                "alice",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        risk = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--json",
                "contributors",
                "risk",
                "alice",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        legacy = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "analysis",
                "meta-bugs",
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert contributor_list.returncode == 0
    jsonl_rows = [json.loads(line) for line in contributor_list.stdout.splitlines() if line.strip()]
    assert jsonl_rows[0]["author_login"] == "alice"
    assert contributor_show.returncode == 0
    assert "EXAMPLE PULL REQUESTS" in contributor_show.stdout
    risk_payload = json.loads(risk.stdout)
    assert risk_payload["risk"]["automation_risk_signal"] == "low"
    assert legacy.returncode == 0
    assert "ISSUE CLUSTERS" in legacy.stdout


@contextmanager
def _json_server(routes: Mapping[str, RoutePayload]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = routes.get(self.path)
            if payload is None:
                self.send_response(404)
                self.end_headers()
                return
            status_code, body_obj = _route_response(payload)
            body = json.dumps(body_obj).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _route_response(payload: RoutePayload) -> tuple[int, object]:
    if isinstance(payload, tuple):
        if len(payload) != 2 or not isinstance(payload[0], int):
            raise TypeError(f"invalid route payload: {payload!r}")
        return payload[0], payload[1]
    return 200, payload
