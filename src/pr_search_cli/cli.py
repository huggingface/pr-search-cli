from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from pr_search_cli.client import PrSearchApiClient
from pr_search_cli.format import (
    format_analysis_best,
    format_analysis_duplicate_prs,
    format_analysis_meta_bug,
    format_analysis_meta_bugs,
    format_analysis_status,
    format_cluster,
    format_cluster_list,
    format_clusters,
    format_pr_analysis,
    format_similar,
    format_status,
)

DEFAULT_BASE_URL = "https://evalstate-openclaw-pr-api.hf.space"
DEFAULT_REPO = "openclaw/openclaw"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-search",
        description="Thin client for the OpenClaw PR similarity API.",
        epilog=(
            "Examples:\n"
            "  pr-search repo status\n"
            "  pr-search analysis status\n"
            "  pr-search analysis pr 67144\n"
            "  pr-search similar 67144\n"
            "  pr-search clusters 67144\n"
            "  pr-search cluster list --limit 20\n"
            "  pr-search --json similar 67144 --mode live\n"
            "  pr-search cluster view pr-scope-64913-2"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="API base URL. Defaults to the deployed Hugging Face Space.",
    )
    parser.add_argument(
        "-R",
        "--repo",
        default=DEFAULT_REPO,
        help=(
            "Repository in owner/name form. The current deployment only supports "
            "openclaw/openclaw, but the flag is accepted for forward compatibility."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit raw JSON from the server.")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    repo_parser = subparsers.add_parser("repo", help="Repository-level operations.")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", required=True)
    repo_subparsers.add_parser("status", help="Show active index status.")

    analysis_parser = subparsers.add_parser("analysis", help="Analysis report operations.")
    analysis_subparsers = analysis_parser.add_subparsers(
        dest="analysis_command",
        required=True,
    )
    analysis_status = analysis_subparsers.add_parser("status", help="Show analysis status.")
    analysis_status.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Analysis report variant. Defaults to auto.",
    )
    analysis_pr = analysis_subparsers.add_parser("pr", help="Show analysis cluster for one PR.")
    analysis_pr.add_argument("number", type=int)
    analysis_pr.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Analysis report variant. Defaults to auto.",
    )
    analysis_meta_bugs = analysis_subparsers.add_parser(
        "meta-bugs",
        help="List analysis meta bugs.",
    )
    analysis_meta_bugs.add_argument(
        "--limit", type=int, default=None, help="Maximum rows to return."
    )
    analysis_meta_bugs.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Analysis report variant. Defaults to auto.",
    )
    analysis_meta_bug = analysis_subparsers.add_parser(
        "meta-bug",
        help="Inspect one analysis meta bug.",
    )
    analysis_meta_bug.add_argument("cluster_id")
    analysis_meta_bug.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Analysis report variant. Defaults to auto.",
    )
    analysis_duplicate_prs = analysis_subparsers.add_parser(
        "duplicate-prs",
        help="List duplicate PR clusters from analysis.",
    )
    analysis_duplicate_prs.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum rows to return.",
    )
    analysis_duplicate_prs.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Analysis report variant. Defaults to auto.",
    )
    analysis_best = analysis_subparsers.add_parser("best", help="Show best issue and PR picks.")
    analysis_best.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Analysis report variant. Defaults to auto.",
    )

    similar = subparsers.add_parser("similar", help="Show similar PRs.")
    similar.add_argument("number", type=int)
    similar.add_argument("--limit", type=int, default=None, help="Maximum rows to return.")
    similar.add_argument(
        "--mode",
        choices=("auto", "indexed", "live"),
        default="auto",
        help="Lookup mode. Defaults to auto.",
    )

    clusters = subparsers.add_parser("clusters", help="Show cluster context for a PR.")
    clusters.add_argument("number", type=int)
    clusters.add_argument("--limit", type=int, default=None, help="Maximum rows to return.")
    clusters.add_argument(
        "--mode",
        choices=("auto", "indexed", "live"),
        default="auto",
        help="Lookup mode. Defaults to auto.",
    )

    cluster_parser = subparsers.add_parser("cluster", help="Cluster operations.")
    cluster_subparsers = cluster_parser.add_subparsers(dest="cluster_command", required=True)
    cluster_list = cluster_subparsers.add_parser("list", help="List clusters.")
    cluster_list.add_argument("--limit", type=int, default=None, help="Maximum rows to return.")
    cluster_view = cluster_subparsers.add_parser("view", help="Inspect one cluster.")
    cluster_view.add_argument("cluster_id")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = PrSearchApiClient(base_url=args.base_url)
    try:
        if args.command == "repo":
            result = client.get_status(args.repo)
            _emit(result, args.json, format_status)
            return

        if args.command == "analysis" and args.analysis_command == "status":
            result = client.get_analysis_status(args.repo, variant=args.variant)
            _emit(result, args.json, format_analysis_status)
            return
        if args.command == "analysis" and args.analysis_command == "pr":
            result = client.get_pr_analysis(args.repo, number=args.number, variant=args.variant)
            _emit(result, args.json, format_pr_analysis)
            return
        if args.command == "analysis" and args.analysis_command == "meta-bugs":
            result = client.list_analysis_meta_bugs(
                args.repo,
                limit=args.limit,
                variant=args.variant,
            )
            _emit(result, args.json, format_analysis_meta_bugs)
            return
        if args.command == "analysis" and args.analysis_command == "meta-bug":
            result = client.get_analysis_meta_bug(
                args.repo,
                cluster_id=args.cluster_id,
                variant=args.variant,
            )
            _emit(result, args.json, format_analysis_meta_bug)
            return
        if args.command == "analysis" and args.analysis_command == "duplicate-prs":
            result = client.list_analysis_duplicate_prs(
                args.repo,
                limit=args.limit,
                variant=args.variant,
            )
            _emit(result, args.json, format_analysis_duplicate_prs)
            return
        if args.command == "analysis" and args.analysis_command == "best":
            result = client.get_analysis_best(args.repo, variant=args.variant)
            _emit(result, args.json, format_analysis_best)
            return

        if args.command == "similar":
            result = client.get_similar(
                args.repo,
                number=args.number,
                limit=args.limit,
                mode=args.mode,
            )
            _emit(result, args.json, format_similar)
            return

        if args.command == "clusters":
            result = client.get_clusters(
                args.repo,
                number=args.number,
                limit=args.limit,
                mode=args.mode,
            )
            _emit(result, args.json, format_clusters)
            return

        if args.command == "cluster" and args.cluster_command == "view":
            result = client.get_cluster(args.repo, cluster_id=args.cluster_id)
            _emit(result, args.json, format_cluster)
            return
        if args.command == "cluster" and args.cluster_command == "list":
            result = client.list_clusters(args.repo, limit=args.limit)
            _emit(result, args.json, format_cluster_list)
            return

        raise RuntimeError("unsupported command")
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _emit(
    payload: dict[str, Any],
    as_json: bool,
    formatter: Callable[[dict[str, Any]], str],
) -> None:
    print(json.dumps(payload, indent=2) if as_json else formatter(payload))
