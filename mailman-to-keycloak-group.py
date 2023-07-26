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
from krs.users import list_users

NON_ICECUBE_MEMBER_MESSAGE = """
You are receiving this messages because you need to take action to
avoid disruption in delivery of messages from mailing list
{list_addr}.

In the near future this mailing list will become restricted to
active members of {experiment_list} experiment(s),
and require subscriber to use their IceCube email addresses.

You are currently subscribed to {list_addr} using
{user_addr}, which is either a non-IceCube, or a disallowed email address.

In order to remain subscribed to {list_addr} after enforcement
of membership restrictions begins you must:
(1) join the corresponding mailing list group, and,
(2) ensure that you are a member of an institution belonging to
one of {experiment_list} experiment(s).

- Go to https://user-management.icecube.aq
- Log in using your IceCube credentials
- Under "Groups" at the bottom of the page, click "Join a group"
- Select the appropriate group (look for prefix "/mail/")
- Click "Submit Join Request"

If you are not a member of an institution belonging to
{experiment_list} experiment(s):
- Under "Experiments/Institutions", click "Join an institution"
- Select an experiment and an institution
- Click "Submit Join Request"

In order to avoid disruption in receiving of messages from
{list_addr} once it becomes restricted,
you must complete the steps above, and your requests
must be approved prior to the transition.

Taking the steps above will not affect your current subscription,
so we recommend completing them soon, since it may take some time
for requests to get approved.

If you have questions or need help, please email help@icecube.wisc.edu.
"""

NON_ICECUBE_OWNER_MESSAGE = """
You are receiving this message because you are registered as an owner of
{list_addr} using {user_addr}, which is either
a non-IceCube or a disallowed email address.

In the near future this mailing list will become restricted to
active members of {experiment_list} experiment(s),
and only allow email addresses ending in @icecube.wisc.edu.

In order to remain an owner of {list_addr} after the transition,
you must send a request to help@icecube.wisc.edu. For example:

Please make <YOUR_ICECUBE_USERNAME> an administrator of the
controlled mailing list {list_addr}.
"""

logger = logging.getLogger("member-import")
logger.propagate = False


class ColorLoggingFormatter(logging.Formatter):
    def __init__(self, /, dryrun):
        super().__init__()

        yellow = "\x1b[33;20m"
        red = "\x1b[31;20m"
        inv_red = "\x1b[31;7m"
        reset = "\x1b[0m"
        fmt = "%(levelname)s: %(message)s"

        self.FORMATS = {
            logging.DEBUG: fmt + f" [dryrun={dryrun}]",
            logging.INFO: fmt + f" [dryrun={dryrun}]",
            logging.WARNING: yellow + fmt + f" [dryrun={dryrun}]" + reset,
            logging.ERROR: red + fmt + f" [dryrun={dryrun}]" + reset,
            logging.CRITICAL: inv_red + fmt + f" [dryrun={dryrun}]" + reset,
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def send_email(smtp_host, to, subj, message):
    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = "no-reply@icecube.wisc.edu"
    msg["To"] = "vbrik@icecube.wisc.edu"
    msg.set_content(message)
    with smtplib.SMTP(smtp_host) as s:
        s.send_message(msg)


async def mailman_to_keycloak_member_import(
    mmcfg,
    keycloak_group,
    mail_server,
    required_experiments,
    keycloak,
    dryrun,
):
    logger.info("Creating groups")
    if not dryrun:
        await create_group(keycloak_group, rest_client=keycloak)
        await create_group(keycloak_group + "/_admin", rest_client=keycloak)

    all_users = await list_users(rest_client=keycloak)
    canon_addrs = {
        u["attributes"]["canonical_email"]: u["username"]
        for u in all_users.values()
        if "canonical_email" in u["attributes"]
    }

    send_regular_instructions_to = set()
    for email in mmcfg["digest_members"] + mmcfg["regular_members"]:
        username, domain = email.split("@")
        if domain == "icecube.wisc.edu":
            username = canon_addrs.get(email, username)
            if username not in all_users:
                logger.warning(f"Unknown user {email}")
                send_regular_instructions_to.add(email)
                continue
            logger.info(f"Adding {username} as MEMBER")
            if not dryrun:
                await add_user_group(keycloak_group, username, rest_client=keycloak)
        else:
            logger.info(f"Non-icecube member {email}")
            send_regular_instructions_to.add(email)

    for email in send_regular_instructions_to:
        logger.info(f"Sending MEMBER instructions to {email}")
        if not dryrun:
            send_email(
                mail_server,
                email,
                f"Important information about membership in mailing list {mmcfg['email']}",
                NON_ICECUBE_MEMBER_MESSAGE.format(
                    list_addr=mmcfg["email"],
                    user_addr=email,
                    experiment_list=', '.join(required_experiments),
                ),
            )

    send_owner_instructions_to = set()
    for email in mmcfg["owner"]:
        username, domain = email.split("@")
        if domain == "icecube.wisc.edu":
            username = canon_addrs.get(email, username)
            if username not in all_users:
                logger.warning(f"Unknown owner {email}")
                send_owner_instructions_to.add(email)
                continue
            logger.info(f"Adding {username} as OWNER")
            if not dryrun:
                await add_user_group(keycloak_group + "/_admin", username, rest_client=keycloak)
        else:
            logger.info(f"Non-icecube owner {email}")
            send_owner_instructions_to.add(email)

    for email in send_owner_instructions_to:
        logger.info(f"Sending OWNER instructions to {email}")
        if not dryrun:
            send_email(
                mail_server,
                email,
                f"Important information about ownership of mailing list {mmcfg['email']}",
                NON_ICECUBE_OWNER_MESSAGE.format(
                    list_addr=mmcfg["email"],
                    user_addr=email,
                    experiment_list=', '.join(required_experiments),
                ),
            )


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
        "--required-experiments",
        metavar="NAME",
        required=True,
        nargs="+",
        help="experiment(s) to use in instructions emails",
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
        "--mail-server",
        metavar="HOST",
        required=True,
        help="use HOST to send instructional emails",
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

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    handler = logging.StreamHandler()
    handler.setFormatter(ColorLoggingFormatter(dryrun=args.dry_run))
    logger.addHandler(handler)
    ClientCredentialsAuth = logging.getLogger('ClientCredentialsAuth')
    ClientCredentialsAuth.setLevel(logging.WARNING)

    logger.info(f"Loading mailman list configuration from {args.mailman_pickle}")
    with open(args.mailman_pickle, "rb") as f:
        mmcfg = pickle.load(f)

    keycloak = get_rest_client()

    asyncio.run(
        mailman_to_keycloak_member_import(
            mmcfg,
            args.keycloak_group,
            args.mail_server,
            args.required_experiments,
            keycloak,
            args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())