#!/usr/bin/env python
import argparse
import logging
import pickle
import sys

from krs.token import get_rest_client
from krs.groups import get_group_membership, group_info, remove_user_group, modify_group
from krs.users import user_info, list_users

def main():
    def __formatter(max_help_position, width):
        return lambda prog: argparse.ArgumentDefaultsHelpFormatter(
            prog, max_help_position=max_help_position, width=width
        )

    parser = argparse.ArgumentParser(
        description="XXX",
        epilog="XXX",
        formatter_class=__formatter(30, 90),
    )
    parser.add_argument(
        "--mailman-pickle",
        metavar="PATH",
        required=True,
        help="mailman list configuration pickle file created by pickle-mailman-list.py",
    )
    parser.add_argument(
        "--keycloak-group",
        metavar="PATH",
        required=True,
        help="path to the KeyCloak group to populate",
    )
    parser.add_argument("--ignore", metavar="EMAIL", default=[], nargs="*", help="don't add EMAIL to group members")
    parser.add_argument(
        "--extra-admins",
        metavar="EMAIL",
        default=[],
        nargs="*",
        help="add these users to the list's _admin subgroup",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="perform a trial run with no changes made",
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="logging level: debug, info, warning, error",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)s %(message)s",
    )

    logging.info(f"Retrieving mailman list configuration from {args.list_pkl}")
    with open(args.list_pkl, "rb") as f:
        mmcfg = pickle.load(f)

    keycloak_client = get_rest_client()


    # mmcfg["digest_members"]
    # mmcfg["regular_members"]
    # mmcfg["owner"]


if __name__ == "__main__":
    sys.exit(main())
