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
