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
    assert "similar 67144" in result.stdout
    assert "clusters 67144" in result.stdout
    assert "cluster list --limit 20" in result.stdout
    assert "analysis pr 67144" in result.stdout


def test_status_and_similar_json() -> None:
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
            [sys.executable, "-m", "pr_search_cli", "--base-url", base_url, "repo", "status"],
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
                "--json",
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
    assert "Repo: openclaw/openclaw" in status.stdout
    payload = json.loads(similar.stdout)
    assert payload["similar_prs"][0]["neighbor_pr_number"] == 99


def test_analysis_status_and_pr_text() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/analysis/status?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "variant_requested": "auto",
            "available": True,
            "variant_used": "hybrid",
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "counts": {
                "meta_bugs": 3,
                "duplicate_issues": 1,
                "duplicate_prs": 2,
            },
        },
        "/v1/repos/openclaw/openclaw/pulls/123/analysis?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "pr_number": 123,
            "found": True,
            "meta_bug": {
                "rank": 1,
                "cluster_id": "cluster-123-2",
                "summary": "CI regression",
                "status": "open",
                "confidence": 0.93,
                "canonical_issue_number": 100,
                "canonical_pr_number": 123,
                "issue_numbers": [100],
                "pr_numbers": [123, 124],
                "evidence_types": ["closing_reference"],
            },
            "duplicate_pr": {
                "cluster_id": "cluster-123-2",
                "canonical_pr_number": 123,
                "duplicate_pr_numbers": [124],
                "target_issue_number": 100,
                "reason": "Same fix path.",
            },
        },
    }
    with _json_server(routes) as base_url:
        status = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "analysis",
                "status",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )
        pr = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "analysis",
                "pr",
                "123",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert status.returncode == 0
    assert "Variant used: hybrid" in status.stdout
    assert "LLM enrichment: yes" in status.stdout
    assert pr.returncode == 0
    assert "Meta bug: cluster-123-2" in pr.stdout
    assert "Duplicates: #124" in pr.stdout


def test_analysis_meta_bugs_and_best_json() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/analysis/meta-bugs?variant=auto&limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "meta_bug_count": 1,
            "meta_bugs": [
                {
                    "rank": 1,
                    "cluster_id": "cluster-123-2",
                    "summary": "CI regression",
                    "status": "open",
                    "confidence": 0.93,
                    "canonical_issue_number": 100,
                    "canonical_pr_number": 123,
                    "issue_numbers": [100],
                    "pr_numbers": [123, 124],
                    "evidence_types": ["closing_reference"],
                }
            ],
        },
        "/v1/repos/openclaw/openclaw/analysis/best?variant=auto": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "variant_requested": "auto",
            "variant_used": "hybrid",
            "llm_enrichment": True,
            "generated_at": "2026-04-16T12:00:00Z",
            "best_issue": {
                "cluster_id": "cluster-123-2",
                "issue_number": 100,
                "reason": "Best issue.",
                "score": 0.91,
            },
            "best_pr": {
                "cluster_id": "cluster-123-2",
                "pr_number": 123,
                "reason": "Best PR.",
                "score": 0.92,
            },
        },
    }
    with _json_server(routes) as base_url:
        meta_bugs = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--json",
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
        best = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--json",
                "analysis",
                "best",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert meta_bugs.returncode == 0
    assert json.loads(meta_bugs.stdout)["meta_bugs"][0]["cluster_id"] == "cluster-123-2"
    assert best.returncode == 0
    assert json.loads(best.stdout)["best_pr"]["cluster_id"] == "cluster-123-2"


def test_clusters_json() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/pulls/123/clusters?mode=auto&limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "assigned_cluster_count": 1,
            "candidate_cluster_count": 1,
            "query": {
                "pr_number": 123,
                "mode_requested": "auto",
                "mode_used": "indexed",
                "source": "active_index",
            },
            "pr": {"pr_number": 123, "title": "Fix CI"},
            "assigned_clusters": [
                {
                    "cluster_id": "pr-scope-99-2",
                    "representative_pr_number": 99,
                    "cluster_size": 2,
                    "average_similarity": 0.91,
                    "summary": "CI-related changes.",
                    "shared_filenames": ["src/ci.py"],
                    "shared_directories": [],
                }
            ],
            "candidate_clusters": [
                {
                    "cluster_id": "pr-scope-99-2",
                    "candidate_score": 0.92,
                    "assigned": True,
                    "representative_pr_number": 99,
                    "matched_member_pr_numbers": [99],
                    "reason": "overlapping files",
                }
            ],
        }
    }
    with _json_server(routes) as base_url:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "--json",
                "clusters",
                "123",
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["assigned_clusters"][0]["cluster_id"] == "pr-scope-99-2"


def test_cluster_list_text() -> None:
    routes = {
        "/v1/repos/openclaw/openclaw/clusters?limit=2": {
            "repo": "openclaw/openclaw",
            "snapshot_id": "20260416T120000Z",
            "run_id": "run-1",
            "cluster_count": 1,
            "clusters": [
                {
                    "rank": 1,
                    "cluster_id": "pr-scope-99-2",
                    "representative_pr_number": 99,
                    "cluster_size": 2,
                    "average_similarity": 0.91,
                    "summary": "CI-related changes.",
                    "representative_title": "Fix CI",
                    "shared_filenames": ["src/ci.py"],
                    "shared_directories": [],
                }
            ],
        }
    }
    with _json_server(routes) as base_url:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pr_search_cli",
                "--base-url",
                base_url,
                "cluster",
                "list",
                "--limit",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=TEST_ENV,
        )

    assert result.returncode == 0
    assert "Clusters:" in result.stdout
    assert "Clusters returned: 1" in result.stdout
    assert "pr-scope-99-2" in result.stdout


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
