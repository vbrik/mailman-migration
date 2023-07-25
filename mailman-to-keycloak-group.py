#!/usr/bin/env python
import argparse
import asyncio
import logging
import pickle
import smtplib
import sys

from email.message import EmailMessage

from krs.token import get_rest_client
from krs.groups import create_group, add_user_group
from krs.users import user_info, list_users


def send_instructions_email(smtp_host, username, list_email):
    msg = EmailMessage()
    msg['Subject'] = f"You have been unsubscribed from {list_email}"
    msg['From'] = 'no-reply@icecube.wisc.edu'
    msg['To'] = f'{username}@icecube.wisc.edu'
    content = f"""You have been unsubscribed from {list_email}
because you are not a member of any of the
institutions that are allowed for that mailing list.

Please contact help@icecube.wisc.edu if you have questions.
"""
    msg.set_content(content)
    with smtplib.SMTP(smtp_host) as s:
        s.send_message(msg)


async def mailman_to_keycloak_group(mmcfg, keycloak_group, keycloak, dryrun):
    await create_group(keycloak_group, rest_client=keycloak)
    await create_group(keycloak_group + "/_admin", rest_client=keycloak)

    all_users = await list_users(rest_client=keycloak)
    canon_addrs = {
        u["attributes"]["canonical_email"]: u["username"]
        for u in all_users.values()
        if "canonical_email" in u["attributes"]
    }

    for email in mmcfg["digest_members"] + mmcfg["regular_members"]:
        username, domain = email.split('@')
        if domain == 'icecube.wisc.edu':
            username = canon_addrs.get(email, username)
            if username not in all_users:
                logging.warning(f"Skipping unknown user {email}")
                continue
            await add_user_group(keycloak_group, username, rest_client=keycloak)
        else:
            logging.warning(f"Non-icecube email {email}")

    for email in mmcfg["owner"]:
        username, domain = email.split('@')
        if domain == 'icecube.wisc.edu':
            username = canon_addrs.get(email, username)
            if username not in all_users:
                logging.warning(f"Skipping unknown owner {email}")
                continue
            await add_user_group(keycloak_group + '/_admin', username, rest_client=keycloak)
        else:
            logging.warning(f"Non-icecube owner email {email}")



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
    parser.add_argument(
        "--ignore",
        metavar="EMAIL",
        default=[],
        nargs="*",
        help="don't add EMAIL to group members",
    )
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
#        format="%(levelname)s %(message)s",
    )

    logging.info(f"Loading mailman list configuration from {args.mailman_pickle}")
    with open(args.mailman_pickle, "rb") as f:
        mmcfg = pickle.load(f)

    keycloak = get_rest_client()

    asyncio.run(mailman_to_keycloak_group(mmcfg, args.keycloak_group, keycloak, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
