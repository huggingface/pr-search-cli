from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def format_status(result: Mapping[str, Any]) -> str:
    counts = result["row_counts"]
    return "\n".join(
        [
            f"Repo: {result['repo']}",
            f"Active run: {result['id']}",
            f"Snapshot: {result['snapshot_id']}",
            f"Source: {result['source_type']}",
            f"Finished: {result.get('finished_at') or 'running'}",
            (
                "Rows: "
                f"documents={counts['documents']} "
                f"features={counts['features']} "
                f"neighbors={counts['neighbors']} "
                f"clusters={counts['clusters']} "
                f"candidates={counts['cluster_candidates']}"
            ),
        ]
    )


def format_similar(result: Mapping[str, Any]) -> str:
    query = result.get("query") or {}
    mode_used = str(query.get("mode_used") or "indexed")
    source = str(query.get("source") or "active_index")
    lines = [
        f"PR #{result['pr']['pr_number']}: {result['pr']['title']}",
        "",
        f"Active snapshot: {result['snapshot_id']}",
        f"Lookup: {mode_used} via {source}",
        f"Matches: {result.get('similar_count', len(result['similar_prs']))}",
        "",
    ]
    if not result["similar_prs"]:
        lines.append("No similar PRs found in the active run.")
        return "\n".join(lines)
    for index, row in enumerate(result["similar_prs"], start=1):
        lines.append(f"{index}. PR #{row['neighbor_pr_number']}  score={row['similarity']:.2f}")
        lines.append(
            "   "
            f"content={row['content_similarity']:.2f} "
            f"size={row['size_similarity']:.2f} "
            f"breadth={row['breadth_similarity']:.2f} "
            f"concentration={row['concentration_similarity']:.2f}"
        )
        if row["shared_filenames"]:
            lines.append(f"   shared files: {', '.join(row['shared_filenames'][:5])}")
        elif row["shared_directories"]:
            lines.append(f"   shared directories: {', '.join(row['shared_directories'][:5])}")
        if row["cluster_ids"]:
            lines.append(f"   cluster: {row['cluster_ids'][0]}")
    return "\n".join(lines)


def format_clusters(result: Mapping[str, Any]) -> str:
    query = result.get("query") or {}
    mode_used = str(query.get("mode_used") or "indexed")
    source = str(query.get("source") or "active_index")
    lines = [
        f"PR #{result['pr']['pr_number']}: cluster context",
        "",
        f"Lookup: {mode_used} via {source}",
        f"Assigned: {result.get('assigned_cluster_count', len(result.get('assigned_clusters') or []))}",
        f"Candidates: {result.get('candidate_cluster_count', len(result.get('candidate_clusters') or []))}",
        "",
        "Assigned clusters:",
    ]
    assigned_clusters = result.get("assigned_clusters") or []
    if not assigned_clusters:
        lines.append("- none")
    else:
        for cluster in assigned_clusters:
            lines.append(
                f"- {cluster['cluster_id']}  representative=PR #{cluster['representative_pr_number']}  "
                f"size={cluster['cluster_size']}"
            )
            if cluster.get("summary"):
                lines.append(f"  {cluster['summary']}")
    lines.extend(["", "Candidate clusters:"])
    candidates = result.get("candidate_clusters") or []
    if not candidates:
        lines.append("- none")
        return "\n".join(lines)
    for index, row in enumerate(candidates, start=1):
        lines.append(
            f"{index}. {row['cluster_id']}  score={row['candidate_score']:.2f}  "
            f"assigned={'yes' if row['assigned'] else 'no'}"
        )
        lines.append(f"   representative: PR #{row['representative_pr_number']}")
        matched = row.get("matched_member_pr_numbers") or []
        if matched:
            lines.append(f"   matched members: {', '.join(f'#{number}' for number in matched)}")
        if row.get("reason"):
            lines.append(f"   reason: {row['reason']}")
    return "\n".join(lines)


def format_cluster(result: Mapping[str, Any]) -> str:
    cluster = result["cluster"]
    lines = [
        f"Cluster {cluster['cluster_id']}",
        f"Representative PR: #{cluster['representative_pr_number']}",
        f"Members: {result.get('member_count', len(result['members']))}",
        f"Average similarity: {cluster['average_similarity']:.2f}",
        cluster["summary"],
        "",
        "Members:",
    ]
    for member in result["members"]:
        suffix = " (representative)" if member["member_role"] == "representative" else ""
        title = member.get("title") or ""
        lines.append(f"- PR #{member['pr_number']}{suffix}: {title}")
    return "\n".join(lines)


def format_cluster_list(result: Mapping[str, Any]) -> str:
    lines = [
        f"Repo: {result['repo']}",
        f"Active snapshot: {result['snapshot_id']}",
        f"Clusters returned: {result.get('cluster_count', len(result.get('clusters') or []))}",
        "",
        "Clusters:",
    ]
    clusters = result.get("clusters") or []
    if not clusters:
        lines.append("- none")
        return "\n".join(lines)
    for index, cluster in enumerate(clusters, start=1):
        lines.append(
            f"{cluster.get('rank', index)}. {cluster['cluster_id']}  representative=PR #{cluster['representative_pr_number']}  "
            f"size={cluster['cluster_size']} avg={cluster['average_similarity']:.2f}"
        )
        if cluster.get("representative_title"):
            lines.append(f"   {cluster['representative_title']}")
        if cluster.get("summary"):
            lines.append(f"   {cluster['summary']}")
    return "\n".join(lines)
