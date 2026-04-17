from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class PrSearchApiClient:
    def __init__(self, *, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get_status(self, repo: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(f"/v1/repos/{owner}/{name}/status")

    def get_similar(
        self,
        repo: str,
        *,
        number: int,
        limit: int | None,
        mode: str,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/pulls/{number}/similar",
            params=_lookup_params(limit=limit, mode=mode),
        )

    def get_clusters(
        self,
        repo: str,
        *,
        number: int,
        limit: int | None,
        mode: str,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/pulls/{number}/clusters",
            params=_lookup_params(limit=limit, mode=mode),
        )

    def get_cluster(self, repo: str, *, cluster_id: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        encoded_cluster_id = urllib.parse.quote(cluster_id, safe="")
        return self._get_json(f"/v1/repos/{owner}/{name}/clusters/{encoded_cluster_id}")

    def list_clusters(self, repo: str, *, limit: int | None) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/clusters",
            params=None if limit is None else {"limit": limit},
        )

    def get_issue_status(self, repo: str, *, variant: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/status",
            params={"variant": variant},
        )

    def list_issue_clusters(
        self,
        repo: str,
        *,
        limit: int | None,
        variant: str,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/clusters",
            params=_variant_params(limit=limit, variant=variant),
        )

    def get_issue_cluster(
        self,
        repo: str,
        *,
        cluster_id: str,
        variant: str,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        encoded_cluster_id = urllib.parse.quote(cluster_id, safe="")
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/clusters/{encoded_cluster_id}",
            params={"variant": variant},
        )

    def get_issue_clusters_for_pr(
        self,
        repo: str,
        *,
        number: int,
        variant: str,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/pulls/{number}",
            params={"variant": variant},
        )

    def check_issue_membership(
        self,
        repo: str,
        *,
        number: int,
        variant: str,
        cluster_id: str | None,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        params = {"variant": variant}
        if cluster_id is not None:
            params["cluster_id"] = cluster_id
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/pulls/{number}/membership",
            params=params,
        )

    def list_issue_duplicate_prs(
        self,
        repo: str,
        *,
        limit: int | None,
        variant: str,
    ) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/duplicate-prs",
            params=_variant_params(limit=limit, variant=variant),
        )

    def get_issue_best(self, repo: str, *, variant: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/issues/best",
            params={"variant": variant},
        )

    def get_contributor_status(self, repo: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(f"/v1/repos/{owner}/{name}/contributors/status")

    def list_contributors(self, repo: str, *, limit: int | None) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        return self._get_json(
            f"/v1/repos/{owner}/{name}/contributors",
            params=None if limit is None else {"limit": limit},
        )

    def get_contributor(self, repo: str, *, login: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        encoded_login = urllib.parse.quote(login, safe="")
        return self._get_json(f"/v1/repos/{owner}/{name}/contributors/{encoded_login}")

    def get_contributor_risk(self, repo: str, *, login: str) -> dict[str, Any]:
        owner, name = _split_repo(repo)
        encoded_login = urllib.parse.quote(login, safe="")
        return self._get_json(f"/v1/repos/{owner}/{name}/contributors/{encoded_login}/risk")

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, int | str] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request = urllib.request.Request(f"{self.base_url}{path}{query}")
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(_error_detail(detail, fallback=f"HTTP {exc.code}")) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"request failed: {exc.reason}") from exc
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise RuntimeError(f"expected object payload, got {type(data)!r}")
        return data



def _split_repo(repo: str) -> tuple[str, str]:
    owner, sep, name = repo.partition("/")
    if not sep or not owner or not name:
        raise RuntimeError(f"expected owner/name repo, got {repo!r}")
    return owner, name



def _lookup_params(limit: int | None, *, mode: str) -> dict[str, int | str]:
    params: dict[str, int | str] = {"mode": mode}
    if limit is not None:
        params["limit"] = limit
    return params



def _variant_params(limit: int | None, *, variant: str) -> dict[str, int | str]:
    params: dict[str, int | str] = {"variant": variant}
    if limit is not None:
        params["limit"] = limit
    return params



def _error_detail(detail: str, *, fallback: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return detail.strip() or fallback
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return str(payload["detail"])
    return fallback
