from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from typing import Any

from pr_search_cli.client import PrSearchApiClient
from pr_search_cli.format import (
    CODE_CLUSTER_LIST_FORMATTER,
    CODE_CLUSTER_SHOW_FORMATTER,
    CODE_CLUSTERS_FOR_PR_FORMATTER,
    CODE_SIMILAR_FORMATTER,
    CODE_STATUS_FORMATTER,
    CONTRIBUTOR_LIST_FORMATTER,
    CONTRIBUTOR_RISK_FORMATTER,
    CONTRIBUTOR_SHOW_FORMATTER,
    CONTRIBUTOR_STATUS_FORMATTER,
    ISSUE_BEST_FORMATTER,
    ISSUE_DUPLICATE_PRS_FORMATTER,
    ISSUE_FOR_PR_FORMATTER,
    ISSUE_LIST_FORMATTER,
    ISSUE_MEMBERSHIP_FORMATTER,
    ISSUE_SHOW_FORMATTER,
    ISSUE_STATUS_FORMATTER,
    STATUS_FORMATTER,
    OutputFormatter,
)

DEFAULT_FALLBACK_BASE_URL = "https://evalstate-openclaw-pr-api.hf.space"
DEFAULT_REPO = "openclaw/openclaw"
BASE_URL_ENV_VAR = "PR_SEARCH_BASE_URL"

Handler = Callable[[PrSearchApiClient, argparse.Namespace], dict[str, Any]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-search",
        description=(
            "Search code clusters, issue clusters, and contributor risk information from the "
            "published PR search API."
        ),
        epilog=(
            "Examples:\n"
            "  pr-search status\n"
            "  pr-search code similar 67144\n"
            "  pr-search code clusters for-pr 67144 --mode live\n"
            "  pr-search issues list --variant auto\n"
            "  pr-search issues contains-pr 67144\n"
            "  pr-search contributors show alice\n"
            "  pr-search --format json contributors risk alice"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            f"API base URL. Defaults to ${BASE_URL_ENV_VAR} when set, otherwise to a deployed "
            "Hugging Face Space inferred from --repo."
        ),
    )
    parser.add_argument(
        "-R",
        "--repo",
        default=DEFAULT_REPO,
        help="Repository in owner/name form.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "jsonl", "ids"),
        default="text",
        help="Output format. Defaults to text.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Compatibility alias for --format json.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    _add_status_parser(subparsers)
    _add_code_parser(subparsers)
    _add_issue_parser(subparsers)
    _add_contributor_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    raw_argv = sys.argv[1:] if argv is None else argv
    normalized_argv = _rewrite_legacy_args(raw_argv)
    help_argv = _expand_group_help(normalized_argv)
    args = parser.parse_args(help_argv)
    if args.json:
        if args.format not in {"text", "json"}:
            parser.error("--json cannot be combined with --format jsonl or --format ids")
        args.format = "json"
    args.base_url = _resolve_base_url(args.base_url, args.repo)
    client = PrSearchApiClient(base_url=args.base_url)
    try:
        handler: Handler = args.handler
        formatter: OutputFormatter = args.formatter
        payload = handler(client, args)
        _emit(payload, args.format, formatter)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _add_status_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    status = subparsers.add_parser("status", help="Show repo, code, issue, and contributor status.")
    status.set_defaults(handler=_handle_status, formatter=STATUS_FORMATTER)


def _add_code_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    code = subparsers.add_parser("code", help="Search code similarity and code clusters.")
    code_subparsers = code.add_subparsers(dest="code_command", required=True)

    status = code_subparsers.add_parser("status", help="Show the active code-search index.")
    status.set_defaults(handler=_handle_status, formatter=CODE_STATUS_FORMATTER)

    similar = code_subparsers.add_parser("similar", help="Show similar PRs for one PR.")
    similar.add_argument("number", type=int, help="Pull request number to query.")
    _add_limit_arg(similar)
    _add_mode_arg(similar)
    similar.set_defaults(handler=_handle_code_similar, formatter=CODE_SIMILAR_FORMATTER)

    clusters = code_subparsers.add_parser("clusters", help="Browse code clusters.")
    cluster_subparsers = clusters.add_subparsers(dest="code_cluster_command", required=True)

    for_pr = cluster_subparsers.add_parser("for-pr", help="Show cluster context for one PR.")
    for_pr.add_argument("number", type=int, help="Pull request number to query.")
    _add_limit_arg(for_pr)
    _add_mode_arg(for_pr)
    for_pr.set_defaults(
        handler=_handle_code_clusters_for_pr, formatter=CODE_CLUSTERS_FOR_PR_FORMATTER
    )

    cluster_list = cluster_subparsers.add_parser("list", help="List code clusters.")
    _add_limit_arg(cluster_list)
    cluster_list.set_defaults(
        handler=_handle_code_cluster_list, formatter=CODE_CLUSTER_LIST_FORMATTER
    )

    show = cluster_subparsers.add_parser("show", help="Show one code cluster.")
    show.add_argument("cluster_id", help="Cluster identifier.")
    show.set_defaults(handler=_handle_code_cluster_show, formatter=CODE_CLUSTER_SHOW_FORMATTER)


def _add_issue_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    issues = subparsers.add_parser("issues", help="Search issue clusters and PR membership.")
    issue_subparsers = issues.add_subparsers(dest="issue_command", required=True)

    status = issue_subparsers.add_parser("status", help="Show issue-cluster report availability.")
    _add_variant_arg(status)
    status.set_defaults(handler=_handle_issue_status, formatter=ISSUE_STATUS_FORMATTER)

    issue_list = issue_subparsers.add_parser("list", help="List issue clusters.")
    _add_limit_arg(issue_list)
    _add_variant_arg(issue_list)
    issue_list.set_defaults(handler=_handle_issue_list, formatter=ISSUE_LIST_FORMATTER)

    show = issue_subparsers.add_parser("show", help="Show one issue cluster.")
    show.add_argument("cluster_id", help="Cluster identifier.")
    _add_variant_arg(show)
    show.set_defaults(handler=_handle_issue_show, formatter=ISSUE_SHOW_FORMATTER)

    for_pr = issue_subparsers.add_parser("for-pr", help="Show issue clusters containing a PR.")
    for_pr.add_argument("number", type=int, help="Pull request number to query.")
    _add_variant_arg(for_pr)
    for_pr.set_defaults(handler=_handle_issue_for_pr, formatter=ISSUE_FOR_PR_FORMATTER)

    contains_pr = issue_subparsers.add_parser(
        "contains-pr",
        help="Check whether a PR belongs to any issue cluster or one specific cluster.",
    )
    contains_pr.add_argument("number", type=int, help="Pull request number to query.")
    contains_pr.add_argument(
        "cluster_id",
        nargs="?",
        help="Optional cluster identifier to check directly.",
    )
    _add_variant_arg(contains_pr)
    contains_pr.set_defaults(handler=_handle_issue_membership, formatter=ISSUE_MEMBERSHIP_FORMATTER)

    duplicate_prs = issue_subparsers.add_parser(
        "duplicate-prs",
        help="List duplicate PR clusters derived from issue clustering.",
    )
    _add_limit_arg(duplicate_prs)
    _add_variant_arg(duplicate_prs)
    duplicate_prs.set_defaults(
        handler=_handle_issue_duplicate_prs, formatter=ISSUE_DUPLICATE_PRS_FORMATTER
    )

    best = issue_subparsers.add_parser("best", help="Show the best issue and PR picks.")
    _add_variant_arg(best)
    best.set_defaults(handler=_handle_issue_best, formatter=ISSUE_BEST_FORMATTER)


def _add_contributor_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    contributors = subparsers.add_parser(
        "contributors",
        help="Browse contributor summaries and automation-risk signals.",
    )
    contributor_subparsers = contributors.add_subparsers(dest="contributor_command", required=True)

    status = contributor_subparsers.add_parser(
        "status", help="Show contributor report availability."
    )
    status.set_defaults(handler=_handle_contributor_status, formatter=CONTRIBUTOR_STATUS_FORMATTER)

    contributor_list = contributor_subparsers.add_parser(
        "list", help="List contributors in the report."
    )
    _add_limit_arg(contributor_list)
    contributor_list.set_defaults(
        handler=_handle_contributor_list, formatter=CONTRIBUTOR_LIST_FORMATTER
    )

    show = contributor_subparsers.add_parser("show", help="Show one contributor summary.")
    show.add_argument("login", help="GitHub login.")
    show.set_defaults(handler=_handle_contributor_show, formatter=CONTRIBUTOR_SHOW_FORMATTER)

    risk = contributor_subparsers.add_parser("risk", help="Show one contributor's risk summary.")
    risk.add_argument("login", help="GitHub login.")
    risk.set_defaults(handler=_handle_contributor_risk, formatter=CONTRIBUTOR_RISK_FORMATTER)


def _add_limit_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to return.")


def _add_mode_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mode",
        choices=("auto", "indexed", "live"),
        default="auto",
        help="Lookup mode. Defaults to auto.",
    )


def _add_variant_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--variant",
        choices=("auto", "hybrid", "deterministic"),
        default="auto",
        help="Issue-cluster report variant. Defaults to auto.",
    )


def _handle_status(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.get_status(args.repo)


def _handle_code_similar(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.get_similar(args.repo, number=args.number, limit=args.limit, mode=args.mode)


def _handle_code_clusters_for_pr(
    client: PrSearchApiClient,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.get_clusters(args.repo, number=args.number, limit=args.limit, mode=args.mode)


def _handle_code_cluster_list(
    client: PrSearchApiClient, args: argparse.Namespace
) -> dict[str, Any]:
    return client.list_clusters(args.repo, limit=args.limit)


def _handle_code_cluster_show(
    client: PrSearchApiClient, args: argparse.Namespace
) -> dict[str, Any]:
    return client.get_cluster(args.repo, cluster_id=args.cluster_id)


def _handle_issue_status(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.get_issue_status(args.repo, variant=args.variant)


def _handle_issue_list(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.list_issue_clusters(args.repo, limit=args.limit, variant=args.variant)


def _handle_issue_show(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.get_issue_cluster(args.repo, cluster_id=args.cluster_id, variant=args.variant)


def _handle_issue_for_pr(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.get_issue_clusters_for_pr(args.repo, number=args.number, variant=args.variant)


def _handle_issue_membership(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.check_issue_membership(
        args.repo,
        number=args.number,
        variant=args.variant,
        cluster_id=args.cluster_id,
    )


def _handle_issue_duplicate_prs(
    client: PrSearchApiClient,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.list_issue_duplicate_prs(args.repo, limit=args.limit, variant=args.variant)


def _handle_issue_best(client: PrSearchApiClient, args: argparse.Namespace) -> dict[str, Any]:
    return client.get_issue_best(args.repo, variant=args.variant)


def _handle_contributor_status(
    client: PrSearchApiClient,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.get_contributor_status(args.repo)


def _handle_contributor_list(
    client: PrSearchApiClient,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.list_contributors(args.repo, limit=args.limit)


def _handle_contributor_show(
    client: PrSearchApiClient,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.get_contributor(args.repo, login=args.login)


def _handle_contributor_risk(
    client: PrSearchApiClient,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.get_contributor_risk(args.repo, login=args.login)


def _emit(payload: dict[str, Any], output_format: str, formatter: OutputFormatter) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2))
        return
    if output_format == "text":
        print(formatter.text(payload))
        return
    if output_format == "jsonl":
        if formatter.rows is None:
            print(json.dumps(payload, sort_keys=True))
            return
        for row in formatter.rows(payload):
            print(json.dumps(row, sort_keys=True))
        return
    if output_format == "ids":
        if formatter.ids is None:
            raise RuntimeError("--format ids is not supported for this command")
        for value in formatter.ids(payload):
            if value is not None:
                print(value)
        return
    raise RuntimeError(f"unsupported output format {output_format!r}")


def _resolve_base_url(base_url: str | None, repo: str) -> str:
    if base_url:
        return base_url
    env_base_url = os.environ.get(BASE_URL_ENV_VAR)
    if env_base_url:
        return env_base_url
    inferred = _infer_base_url_from_repo(repo)
    if inferred is not None:
        return inferred
    return DEFAULT_FALLBACK_BASE_URL


def _infer_base_url_from_repo(repo: str) -> str | None:
    repo_name = _repo_name(repo)
    if repo_name is None:
        return None
    return f"https://evalstate-{_space_slug(repo_name)}-pr-api.hf.space"


def _repo_name(repo: str) -> str | None:
    owner, sep, name = repo.strip().partition("/")
    if not sep or not owner or not name:
        return None
    return name


def _space_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or value.strip().lower()


def _rewrite_legacy_args(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    prefix, remainder = _split_global_prefix(list(argv))
    if not remainder:
        return argv
    command = remainder[0]
    if command == "repo" and len(remainder) >= 2 and remainder[1] == "status":
        return [*prefix, "status", *remainder[2:]]
    if command == "similar":
        return [*prefix, "code", "similar", *remainder[1:]]
    if command == "clusters":
        return [*prefix, "code", "clusters", "for-pr", *remainder[1:]]
    if command == "cluster" and len(remainder) >= 2:
        if remainder[1] == "list":
            return [*prefix, "code", "clusters", "list", *remainder[2:]]
        if remainder[1] == "view":
            return [*prefix, "code", "clusters", "show", *remainder[2:]]
    if command == "analysis" and len(remainder) >= 2:
        analysis_command = remainder[1]
        if analysis_command == "status":
            return [*prefix, "issues", "status", *remainder[2:]]
        if analysis_command == "pr":
            return [*prefix, "issues", "for-pr", *remainder[2:]]
        if analysis_command == "meta-bugs":
            return [*prefix, "issues", "list", *remainder[2:]]
        if analysis_command == "meta-bug":
            return [*prefix, "issues", "show", *remainder[2:]]
        if analysis_command == "duplicate-prs":
            return [*prefix, "issues", "duplicate-prs", *remainder[2:]]
        if analysis_command == "best":
            return [*prefix, "issues", "best", *remainder[2:]]
    return argv


def _expand_group_help(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    prefix, remainder = _split_global_prefix(list(argv))
    if remainder in (["code"], ["issues"], ["contributors"]):
        return [*prefix, *remainder, "--help"]
    if remainder in (["code", "clusters"],):
        return [*prefix, *remainder, "--help"]
    return argv


def _split_global_prefix(argv: list[str]) -> tuple[list[str], list[str]]:
    prefix: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--json":
            prefix.append(token)
            index += 1
            continue
        if token in {"--base-url", "-R", "--repo", "--format"} and index + 1 < len(argv):
            prefix.extend(argv[index : index + 2])
            index += 2
            continue
        break
    return prefix, argv[index:]
