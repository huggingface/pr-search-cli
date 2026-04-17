from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OutputFormatter:
    text: Callable[[dict[str, Any]], str]
    rows: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None
    ids: Callable[[dict[str, Any]], list[Any]] | None = None


@dataclass(frozen=True, slots=True)
class TableColumn:
    header: str
    render: Callable[[dict[str, Any]], str]


STATUS_FORMATTER = OutputFormatter(text=lambda payload: format_status(payload))
CODE_STATUS_FORMATTER = OutputFormatter(text=lambda payload: format_code_status(payload))
CODE_SIMILAR_FORMATTER = OutputFormatter(
    text=lambda payload: format_similar(payload),
    rows=lambda payload: list(payload.get("similar_prs") or []),
    ids=lambda payload: [row.get("neighbor_pr_number") for row in payload.get("similar_prs") or []],
)
CODE_CLUSTERS_FOR_PR_FORMATTER = OutputFormatter(
    text=lambda payload: format_clusters(payload),
    rows=lambda payload: _cluster_lookup_rows(payload),
    ids=lambda payload: _deduped_cluster_ids(_cluster_lookup_rows(payload)),
)
CODE_CLUSTER_LIST_FORMATTER = OutputFormatter(
    text=lambda payload: format_cluster_list(payload),
    rows=lambda payload: list(payload.get("clusters") or []),
    ids=lambda payload: [row.get("cluster_id") for row in payload.get("clusters") or []],
)
CODE_CLUSTER_SHOW_FORMATTER = OutputFormatter(
    text=lambda payload: format_cluster(payload),
    rows=lambda payload: list(payload.get("members") or []),
    ids=lambda payload: [row.get("pr_number") for row in payload.get("members") or []],
)
ISSUE_STATUS_FORMATTER = OutputFormatter(text=lambda payload: format_issue_status(payload))
ISSUE_LIST_FORMATTER = OutputFormatter(
    text=lambda payload: format_issue_clusters(payload),
    rows=lambda payload: list(payload.get("clusters") or []),
    ids=lambda payload: [row.get("cluster_id") for row in payload.get("clusters") or []],
)
ISSUE_SHOW_FORMATTER = OutputFormatter(text=lambda payload: format_issue_cluster(payload))
ISSUE_FOR_PR_FORMATTER = OutputFormatter(
    text=lambda payload: format_issue_clusters_for_pr(payload),
    rows=lambda payload: list(payload.get("clusters") or []),
    ids=lambda payload: [row.get("cluster_id") for row in payload.get("clusters") or []],
)
ISSUE_MEMBERSHIP_FORMATTER = OutputFormatter(
    text=lambda payload: format_issue_membership(payload),
    rows=lambda payload: list(payload.get("clusters") or []),
    ids=lambda payload: list(payload.get("matching_cluster_ids") or []),
)
ISSUE_DUPLICATE_PRS_FORMATTER = OutputFormatter(
    text=lambda payload: format_issue_duplicate_prs(payload),
    rows=lambda payload: list(payload.get("duplicate_prs") or []),
    ids=lambda payload: [row.get("cluster_id") for row in payload.get("duplicate_prs") or []],
)
ISSUE_BEST_FORMATTER = OutputFormatter(text=lambda payload: format_issue_best(payload))
CONTRIBUTOR_STATUS_FORMATTER = OutputFormatter(text=lambda payload: format_contributor_status(payload))
CONTRIBUTOR_LIST_FORMATTER = OutputFormatter(
    text=lambda payload: format_contributors(payload),
    rows=lambda payload: list(payload.get("contributors") or []),
    ids=lambda payload: [row.get("author_login") for row in payload.get("contributors") or []],
)
CONTRIBUTOR_SHOW_FORMATTER = OutputFormatter(text=lambda payload: format_contributor(payload))
CONTRIBUTOR_RISK_FORMATTER = OutputFormatter(text=lambda payload: format_contributor_risk(payload))


def format_status(payload: dict[str, Any]) -> str:
    counts = payload.get("row_counts") or {}
    lines = _record(
        [
            ("repo", payload.get("repo")),
            ("active_run", payload.get("id")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("source_type", payload.get("source_type")),
            ("finished_at", payload.get("finished_at") or "running"),
            ("documents", counts.get("documents")),
            ("features", counts.get("features")),
            ("neighbors", counts.get("neighbors")),
            ("clusters", counts.get("clusters")),
            ("cluster_candidates", counts.get("cluster_candidates")),
        ]
    )
    surfaces = payload.get("surfaces") or {}
    if not surfaces:
        return lines
    surface_rows = [
        {
            "surface": "code",
            "available": True,
            "summary": (
                f"documents={counts.get('documents', 0)} clusters={counts.get('clusters', 0)}"
            ),
        },
        {
            "surface": "issues",
            "available": (surfaces.get("issues") or {}).get("available"),
            "summary": _issue_surface_summary(surfaces.get("issues") or {}),
        },
        {
            "surface": "contributors",
            "available": (surfaces.get("contributors") or {}).get("available"),
            "summary": _contributor_surface_summary(surfaces.get("contributors") or {}),
        },
    ]
    return _join_sections(lines, _section("SURFACES", _table(surface_rows, _surface_columns())))



def format_code_status(payload: dict[str, Any]) -> str:
    counts = payload.get("row_counts") or {}
    return _record(
        [
            ("repo", payload.get("repo")),
            ("active_run", payload.get("id")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("source_type", payload.get("source_type")),
            ("finished_at", payload.get("finished_at") or "running"),
            ("documents", counts.get("documents")),
            ("features", counts.get("features")),
            ("neighbors", counts.get("neighbors")),
            ("clusters", counts.get("clusters")),
            ("cluster_candidates", counts.get("cluster_candidates")),
        ]
    )



def format_similar(payload: dict[str, Any]) -> str:
    query = payload.get("query") or {}
    rows = []
    for index, row in enumerate(payload.get("similar_prs") or [], start=1):
        rows.append(
            {
                "rank": index,
                "pr": row.get("neighbor_pr_number"),
                "score": row.get("similarity"),
                "content": row.get("content_similarity"),
                "size": row.get("size_similarity"),
                "breadth": row.get("breadth_similarity"),
                "concentration": row.get("concentration_similarity"),
                "cluster": _first(row.get("cluster_ids")),
                "shared": _shared_label(row),
                "title": row.get("neighbor_title"),
            }
        )
    header = _record(
        [
            ("pr_number", (payload.get("pr") or {}).get("pr_number")),
            ("title", (payload.get("pr") or {}).get("title")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("lookup_mode", query.get("mode_used") or query.get("mode_requested") or "indexed"),
            ("lookup_source", query.get("source") or "active_index"),
            ("similar_count", payload.get("similar_count", len(rows))),
        ]
    )
    return _join_sections(header, _section("SIMILAR PRS", _table(rows, _similar_columns())))



def format_clusters(payload: dict[str, Any]) -> str:
    query = payload.get("query") or {}
    assigned_rows = []
    for row in payload.get("assigned_clusters") or []:
        assigned_rows.append(
            {
                "cluster_id": row.get("cluster_id"),
                "representative_pr": row.get("representative_pr_number"),
                "size": row.get("cluster_size"),
                "avg_similarity": row.get("average_similarity"),
                "summary": row.get("summary"),
            }
        )
    candidate_rows = []
    for row in payload.get("candidate_clusters") or []:
        candidate_rows.append(
            {
                "cluster_id": row.get("cluster_id"),
                "score": row.get("candidate_score"),
                "assigned": row.get("assigned"),
                "representative_pr": row.get("representative_pr_number"),
                "matched_members": _join_numbers(row.get("matched_member_pr_numbers") or []),
                "reason": row.get("reason"),
            }
        )
    header = _record(
        [
            ("pr_number", (payload.get("pr") or {}).get("pr_number")),
            ("title", (payload.get("pr") or {}).get("title")),
            ("lookup_mode", query.get("mode_used") or query.get("mode_requested") or "indexed"),
            ("lookup_source", query.get("source") or "active_index"),
            ("assigned_count", payload.get("assigned_cluster_count", len(assigned_rows))),
            ("candidate_count", payload.get("candidate_cluster_count", len(candidate_rows))),
        ]
    )
    return _join_sections(
        header,
        _section("ASSIGNED CLUSTERS", _table(assigned_rows, _assigned_cluster_columns())),
        _section("CANDIDATE CLUSTERS", _table(candidate_rows, _candidate_cluster_columns())),
    )



def format_cluster(payload: dict[str, Any]) -> str:
    cluster = payload.get("cluster") or {}
    header = _record(
        [
            ("cluster_id", cluster.get("cluster_id")),
            ("representative_pr", cluster.get("representative_pr_number")),
            ("member_count", payload.get("member_count", len(payload.get("members") or []))),
            ("average_similarity", _fmt_float(cluster.get("average_similarity"))),
            ("summary", cluster.get("summary")),
        ]
    )
    rows = [
        {
            "pr": row.get("pr_number"),
            "role": row.get("member_role"),
            "title": row.get("title"),
        }
        for row in payload.get("members") or []
    ]
    return _join_sections(header, _section("MEMBERS", _table(rows, _cluster_member_columns())))



def format_cluster_list(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("cluster_count", payload.get("cluster_count", len(payload.get("clusters") or []))),
        ]
    )
    rows = []
    for row in payload.get("clusters") or []:
        rows.append(
            {
                "rank": row.get("rank"),
                "cluster_id": row.get("cluster_id"),
                "representative_pr": row.get("representative_pr_number"),
                "size": row.get("cluster_size"),
                "avg_similarity": row.get("average_similarity"),
                "title": row.get("representative_title"),
                "summary": row.get("summary"),
            }
        )
    return _join_sections(header, _section("CODE CLUSTERS", _table(rows, _cluster_list_columns())))



def format_issue_status(payload: dict[str, Any]) -> str:
    counts = payload.get("counts") or {}
    return _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("variant_requested", payload.get("variant_requested")),
            ("variant_used", payload.get("variant_used") or "-"),
            ("available", _yes_no(payload.get("available"))),
            ("llm_enrichment", _yes_no(payload.get("llm_enrichment"))),
            ("generated_at", payload.get("generated_at") or "-"),
            ("available_variants", _csv(payload.get("available_variants") or [])),
            ("meta_bugs", counts.get("meta_bugs", 0)),
            ("duplicate_issues", counts.get("duplicate_issues", 0)),
            ("duplicate_prs", counts.get("duplicate_prs", 0)),
        ]
    )



def format_issue_clusters(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("variant_used", payload.get("variant_used") or payload.get("variant_requested")),
            ("llm_enrichment", _yes_no(payload.get("llm_enrichment"))),
            ("cluster_count", payload.get("cluster_count", len(payload.get("clusters") or []))),
        ]
    )
    return _join_sections(
        header,
        _section("ISSUE CLUSTERS", _table(payload.get("clusters") or [], _issue_cluster_columns())),
    )



def format_issue_cluster(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("variant_used", payload.get("variant_used") or payload.get("variant_requested")),
            ("found", _yes_no(payload.get("found"))),
            ("cluster_id", payload.get("cluster_id")),
        ]
    )
    cluster = payload.get("cluster")
    if not cluster:
        return header
    details = _record(
        [
            ("title", cluster.get("title")),
            ("summary", cluster.get("summary")),
            ("status", cluster.get("status")),
            ("confidence", _fmt_float(cluster.get("confidence"))),
            ("canonical_issue", cluster.get("canonical_issue_number")),
            ("canonical_pr", cluster.get("canonical_pr_number")),
            ("evidence", _csv(cluster.get("evidence_types") or [])),
        ]
    )
    return _join_sections(
        header,
        details,
        _section("ISSUES", _table(payload.get("issues") or [], _issue_member_columns())),
        _section("PULL REQUESTS", _table(payload.get("pull_requests") or [], _issue_pr_columns())),
    )



def format_issue_clusters_for_pr(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("variant_used", payload.get("variant_used") or payload.get("variant_requested")),
            ("pr_number", payload.get("pr_number")),
            ("found", _yes_no(payload.get("found"))),
            ("cluster_count", payload.get("cluster_count", len(payload.get("clusters") or []))),
        ]
    )
    return _join_sections(
        header,
        _section("MATCHING ISSUE CLUSTERS", _table(payload.get("clusters") or [], _issue_for_pr_columns())),
    )



def format_issue_membership(payload: dict[str, Any]) -> str:
    return _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("variant_used", payload.get("variant_used") or payload.get("variant_requested")),
            ("pr_number", payload.get("pr_number")),
            ("cluster_id", payload.get("cluster_id") or "-"),
            ("matched", _yes_no(payload.get("matched"))),
            ("matching_cluster_ids", _csv(payload.get("matching_cluster_ids") or [])),
        ]
    )



def format_issue_duplicate_prs(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("variant_used", payload.get("variant_used") or payload.get("variant_requested")),
            ("duplicate_pr_count", payload.get("duplicate_pr_count", len(payload.get("duplicate_prs") or []))),
        ]
    )
    return _join_sections(
        header,
        _section("DUPLICATE PR CLUSTERS", _table(payload.get("duplicate_prs") or [], _duplicate_pr_columns())),
    )



def format_issue_best(payload: dict[str, Any]) -> str:
    best_issue = payload.get("best_issue") or {}
    best_pr = payload.get("best_pr") or {}
    return _join_sections(
        _record(
            [
                ("repo", payload.get("repo")),
                ("snapshot_id", payload.get("snapshot_id")),
                ("variant_used", payload.get("variant_used") or payload.get("variant_requested")),
                ("llm_enrichment", _yes_no(payload.get("llm_enrichment"))),
            ]
        ),
        _section(
            "BEST ISSUE",
            _record(
                [
                    ("issue_number", best_issue.get("issue_number") or "-"),
                    ("title", best_issue.get("title") or "-"),
                    ("cluster_id", best_issue.get("cluster_id") or "-"),
                    ("score", _fmt_float(best_issue.get("score")) or "-"),
                    ("reason", best_issue.get("reason") or "-"),
                ]
            ),
        ),
        _section(
            "BEST PR",
            _record(
                [
                    ("pr_number", best_pr.get("pr_number") or "-"),
                    ("title", best_pr.get("title") or "-"),
                    ("cluster_id", best_pr.get("cluster_id") or "-"),
                    ("score", _fmt_float(best_pr.get("score")) or "-"),
                    ("reason", best_pr.get("reason") or "-"),
                ]
            ),
        ),
    )



def format_contributor_status(payload: dict[str, Any]) -> str:
    return _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("available", _yes_no(payload.get("available"))),
            ("generated_at", payload.get("generated_at") or "-"),
            ("window_days", payload.get("window_days") or "-"),
            ("contributor_count", payload.get("contributor_count", 0)),
        ]
    )



def format_contributors(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("available", _yes_no(payload.get("available"))),
            ("contributor_count", payload.get("contributor_count", len(payload.get("contributors") or []))),
        ]
    )
    return _join_sections(
        header,
        _section("CONTRIBUTORS", _table(payload.get("contributors") or [], _contributor_columns())),
    )



def format_contributor(payload: dict[str, Any]) -> str:
    header = _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("author_login", payload.get("author_login")),
            ("found", _yes_no(payload.get("found"))),
        ]
    )
    summary = payload.get("summary")
    contributor = payload.get("contributor") or {}
    if not summary:
        return header
    examples = contributor.get("examples") if isinstance(contributor.get("examples"), dict) else {}
    pr_examples = list(examples.get("pull_requests") or [])
    issue_examples = list(examples.get("issues") or [])
    return _join_sections(
        header,
        _record(
            [
                ("name", summary.get("name") or "-"),
                ("profile_url", summary.get("profile_url") or "-"),
                ("repo_association", summary.get("repo_association") or "-"),
                ("first_seen_in_snapshot", _yes_no(summary.get("first_seen_in_snapshot"))),
                ("new_to_repo", _yes_no(summary.get("new_to_repo"))),
                ("snapshot_pr_count", summary.get("snapshot_pr_count")),
                ("snapshot_issue_count", summary.get("snapshot_issue_count")),
                ("follow_through_score", summary.get("follow_through_score") or "-"),
                ("breadth_score", summary.get("breadth_score") or "-"),
                ("automation_risk", summary.get("automation_risk_signal") or "-"),
                ("heuristic_note", summary.get("heuristic_note") or "-"),
                ("account_age_days", summary.get("account_age_days") or "-"),
                ("public_pr_count_42d", summary.get("public_pr_count_42d") or "-"),
                ("public_repo_count_42d", summary.get("public_repo_count_42d") or "-"),
            ]
        ),
        _section("EXAMPLE PULL REQUESTS", _table(pr_examples, _contributor_pr_example_columns())),
        _section("EXAMPLE ISSUES", _table(issue_examples, _contributor_issue_example_columns())),
    )



def format_contributor_risk(payload: dict[str, Any]) -> str:
    risk = payload.get("risk") or {}
    return _record(
        [
            ("repo", payload.get("repo")),
            ("snapshot_id", payload.get("snapshot_id")),
            ("author_login", payload.get("author_login")),
            ("found", _yes_no(payload.get("found"))),
            ("risk_available", _yes_no(payload.get("risk_available"))),
            ("automation_risk", risk.get("automation_risk_signal") or "-"),
            ("follow_through_score", risk.get("follow_through_score") or "-"),
            ("breadth_score", risk.get("breadth_score") or "-"),
            ("account_age_days", risk.get("account_age_days") or "-"),
            ("public_pr_count_42d", risk.get("public_pr_count_42d") or "-"),
            ("public_repo_count_42d", risk.get("public_repo_count_42d") or "-"),
            ("report_reason", risk.get("report_reason") or "-"),
            ("heuristic_note", risk.get("heuristic_note") or "-"),
        ]
    )



def _record(items: list[tuple[str, Any]]) -> str:
    width = max((len(key) for key, _ in items), default=0)
    lines = []
    for key, value in items:
        lines.append(f"{key.ljust(width)}  {_display(value)}")
    return "\n".join(lines)



def _section(title: str, body: str) -> str:
    return f"{title}\n{body}" if body else title



def _join_sections(*sections: str) -> str:
    return "\n\n".join(section for section in sections if section)



def _table(rows: list[dict[str, Any]], columns: list[TableColumn]) -> str:
    if not rows:
        return "(none)"
    rendered = [[column.render(row) for column in columns] for row in rows]
    widths = [len(column.header) for column in columns]
    for row in rendered:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    header = "  ".join(column.header.ljust(widths[index]) for index, column in enumerate(columns))
    divider = "  ".join("-" * widths[index] for index in range(len(columns)))
    body = [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rendered
    ]
    return "\n".join([header, divider, *body])



def _surface_columns() -> list[TableColumn]:
    return [
        TableColumn("surface", lambda row: _display(row.get("surface"))),
        TableColumn("available", lambda row: _yes_no(row.get("available"))),
        TableColumn("summary", lambda row: _truncate(_display(row.get("summary")), 72)),
    ]



def _similar_columns() -> list[TableColumn]:
    return [
        TableColumn("rank", lambda row: _display(row.get("rank"))),
        TableColumn("pr", lambda row: _display(row.get("pr"))),
        TableColumn("score", lambda row: _fmt_float(row.get("score"))),
        TableColumn("content", lambda row: _fmt_float(row.get("content"))),
        TableColumn("size", lambda row: _fmt_float(row.get("size"))),
        TableColumn("breadth", lambda row: _fmt_float(row.get("breadth"))),
        TableColumn("concentration", lambda row: _fmt_float(row.get("concentration"))),
        TableColumn("cluster", lambda row: _display(row.get("cluster") or "-")),
        TableColumn("shared", lambda row: _truncate(_display(row.get("shared")), 28)),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 36)),
    ]



def _assigned_cluster_columns() -> list[TableColumn]:
    return [
        TableColumn("cluster_id", lambda row: _display(row.get("cluster_id"))),
        TableColumn("representative_pr", lambda row: _display(row.get("representative_pr"))),
        TableColumn("size", lambda row: _display(row.get("size"))),
        TableColumn("avg_similarity", lambda row: _fmt_float(row.get("avg_similarity"))),
        TableColumn("summary", lambda row: _truncate(_display(row.get("summary")), 54)),
    ]



def _candidate_cluster_columns() -> list[TableColumn]:
    return [
        TableColumn("cluster_id", lambda row: _display(row.get("cluster_id"))),
        TableColumn("score", lambda row: _fmt_float(row.get("score"))),
        TableColumn("assigned", lambda row: _yes_no(row.get("assigned"))),
        TableColumn("representative_pr", lambda row: _display(row.get("representative_pr"))),
        TableColumn("matched_members", lambda row: _display(row.get("matched_members") or "-")),
        TableColumn("reason", lambda row: _truncate(_display(row.get("reason")), 48)),
    ]



def _cluster_member_columns() -> list[TableColumn]:
    return [
        TableColumn("pr", lambda row: _display(row.get("pr"))),
        TableColumn("role", lambda row: _display(row.get("role"))),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 68)),
    ]



def _cluster_list_columns() -> list[TableColumn]:
    return [
        TableColumn("rank", lambda row: _display(row.get("rank"))),
        TableColumn("cluster_id", lambda row: _display(row.get("cluster_id"))),
        TableColumn("representative_pr", lambda row: _display(row.get("representative_pr"))),
        TableColumn("size", lambda row: _display(row.get("size"))),
        TableColumn("avg_similarity", lambda row: _fmt_float(row.get("avg_similarity"))),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 28)),
        TableColumn("summary", lambda row: _truncate(_display(row.get("summary")), 38)),
    ]



def _issue_cluster_columns() -> list[TableColumn]:
    return [
        TableColumn("rank", lambda row: _display(row.get("rank"))),
        TableColumn("cluster_id", lambda row: _display(row.get("cluster_id"))),
        TableColumn("issue", lambda row: _display(row.get("canonical_issue_number") or "-")),
        TableColumn("canonical_pr", lambda row: _display(row.get("canonical_pr_number") or "-")),
        TableColumn("prs", lambda row: _display(row.get("pr_count") or 0)),
        TableColumn("status", lambda row: _display(row.get("status") or "-")),
        TableColumn("confidence", lambda row: _fmt_float(row.get("confidence"))),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 30)),
        TableColumn("summary", lambda row: _truncate(_display(row.get("summary")), 38)),
    ]



def _issue_member_columns() -> list[TableColumn]:
    return [
        TableColumn("number", lambda row: _display(row.get("number"))),
        TableColumn("state", lambda row: _display(row.get("state") or "-")),
        TableColumn("author", lambda row: _display(row.get("author_login") or "-")),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 52)),
    ]



def _issue_pr_columns() -> list[TableColumn]:
    return [
        TableColumn("number", lambda row: _display(row.get("number"))),
        TableColumn("role", lambda row: _display(row.get("role") or "-")),
        TableColumn("author", lambda row: _display(row.get("author_login") or "-")),
        TableColumn("state", lambda row: _display(row.get("state") or "-")),
        TableColumn("merged", lambda row: _yes_no(row.get("merged"))),
        TableColumn("draft", lambda row: _yes_no(row.get("draft"))),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 46)),
    ]



def _issue_for_pr_columns() -> list[TableColumn]:
    return [
        TableColumn("cluster_id", lambda row: _display(row.get("cluster_id"))),
        TableColumn("role", lambda row: _display(row.get("membership_role") or "-")),
        TableColumn("issue", lambda row: _display(row.get("canonical_issue_number") or "-")),
        TableColumn("canonical_pr", lambda row: _display(row.get("canonical_pr_number") or "-")),
        TableColumn("status", lambda row: _display(row.get("status") or "-")),
        TableColumn("confidence", lambda row: _fmt_float(row.get("confidence"))),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 34)),
    ]



def _duplicate_pr_columns() -> list[TableColumn]:
    return [
        TableColumn("rank", lambda row: _display(row.get("rank"))),
        TableColumn("cluster_id", lambda row: _display(row.get("cluster_id"))),
        TableColumn("target_issue", lambda row: _display(row.get("target_issue_number") or "-")),
        TableColumn("canonical_pr", lambda row: _display(row.get("canonical_pr_number") or "-")),
        TableColumn("duplicates", lambda row: _join_numbers(row.get("duplicate_pr_numbers") or [])),
        TableColumn("reason", lambda row: _truncate(_display(row.get("reason")), 48)),
    ]



def _contributor_columns() -> list[TableColumn]:
    return [
        TableColumn("rank", lambda row: _display(row.get("rank"))),
        TableColumn("author", lambda row: _display(row.get("author_login"))),
        TableColumn("association", lambda row: _display(row.get("repo_association") or "-")),
        TableColumn("snapshot_prs", lambda row: _display(row.get("snapshot_pr_count") or 0)),
        TableColumn("snapshot_issues", lambda row: _display(row.get("snapshot_issue_count") or 0)),
        TableColumn("first_seen", lambda row: _yes_no(row.get("first_seen_in_snapshot"))),
        TableColumn("risk", lambda row: _display(row.get("automation_risk_signal") or "-")),
        TableColumn("note", lambda row: _truncate(_display(row.get("heuristic_note")), 42)),
    ]



def _contributor_pr_example_columns() -> list[TableColumn]:
    return [
        TableColumn("number", lambda row: _display(row.get("number"))),
        TableColumn("state", lambda row: _display(row.get("state") or "-")),
        TableColumn("merged", lambda row: _yes_no(row.get("merged"))),
        TableColumn("draft", lambda row: _yes_no(row.get("draft"))),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 58)),
    ]



def _contributor_issue_example_columns() -> list[TableColumn]:
    return [
        TableColumn("number", lambda row: _display(row.get("number"))),
        TableColumn("state", lambda row: _display(row.get("state") or "-")),
        TableColumn("title", lambda row: _truncate(_display(row.get("title")), 64)),
    ]



def _issue_surface_summary(row: dict[str, Any]) -> str:
    if not row.get("available"):
        return "unavailable"
    return (
        f"variant={row.get('variant_used') or '-'} clusters={row.get('cluster_count', 0)} "
        f"duplicate_prs={row.get('duplicate_pr_count', 0)}"
    )



def _contributor_surface_summary(row: dict[str, Any]) -> str:
    if not row.get("available"):
        return "unavailable"
    return f"contributors={row.get('contributor_count', 0)}"



def _cluster_lookup_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("assigned_clusters") or []:
        rows.append({"kind": "assigned", **row})
    for row in payload.get("candidate_clusters") or []:
        rows.append({"kind": "candidate", **row})
    return rows



def _deduped_cluster_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        cluster_id = row.get("cluster_id")
        if not cluster_id or cluster_id in seen:
            continue
        seen.add(str(cluster_id))
        ordered.append(str(cluster_id))
    return ordered



def _shared_label(row: dict[str, Any]) -> str:
    shared_files = row.get("shared_filenames") or []
    if shared_files:
        return _csv(shared_files[:3])
    shared_directories = row.get("shared_directories") or []
    if shared_directories:
        return _csv(shared_directories[:3])
    return "-"



def _first(values: Any) -> Any:
    if isinstance(values, list) and values:
        return values[0]
    return None



def _display(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return _yes_no(value)
    return str(value)



def _fmt_float(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"



def _yes_no(value: Any) -> str:
    return "yes" if bool(value) else "no"



def _csv(values: list[Any]) -> str:
    filtered = [str(value) for value in values if value is not None and str(value)]
    return ", ".join(filtered) if filtered else "-"



def _join_numbers(values: list[Any]) -> str:
    filtered = [f"#{value}" for value in values if value is not None]
    return ", ".join(filtered) if filtered else "-"



def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: width - 1].rstrip() + "…"
