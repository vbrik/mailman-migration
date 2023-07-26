#!/usr/bin/env python
import argparse
import sys
import logging
import pickle
from pprint import pformat
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError


def get_google_group_config_from_mailman_config(mmcfg):
    # https://developers.google.com/admin-sdk/groups-settings/v1/reference/groups#json
    if mmcfg["advertised"] and mmcfg["archive"]:
        if mmcfg["archive_private"]:
            who_can_view_group = "ALL_MEMBERS_CAN_VIEW"
        else:
            who_can_view_group = "ALL_IN_DOMAIN_CAN_VIEW"
    else:  # not advertised or not archived
        who_can_view_group = "ALL_MANAGERS_CAN_VIEW"

    if mmcfg["generic_nonmember_action"] in (0, 1):  # accept, hold
        who_can_post_message = "ANYONE_CAN_POST"
    else:  # reject, discard
        who_can_post_message = "ALL_MEMBERS_CAN_POST"
    if mmcfg["default_member_moderation"] and mmcfg["member_moderation_action"] in (
        1,
        2,
    ):  # reject or discard
        who_can_post_message = "NONE_CAN_POST"

    if mmcfg["generic_nonmember_action"] == 0:  # accept
        message_moderation_level = "MODERATE_NONE"
    else:  # hold, reject, discard
        message_moderation_level = "MODERATE_NON_MEMBERS"
    if mmcfg["default_member_moderation"]:
        message_moderation_level = "MODERATE_ALL_MESSAGES"

    if mmcfg["private_roster"] == 0:
        who_can_view_membership = "ALL_IN_DOMAIN_CAN_VIEW"
    elif mmcfg["private_roster"] == 1:
        who_can_view_membership = "ALL_MEMBERS_CAN_VIEW"
    else:
        who_can_view_membership = "ALL_MANAGERS_CAN_VIEW"

    ggcfg = {
        "email": mmcfg["email"],
        "name": mmcfg["real_name"],
        "description": (
            mmcfg["description"] + "\n" + mmcfg["info"] if mmcfg["info"] else mmcfg["description"]
        ),
        "whoCanJoin": "CAN_REQUEST_TO_JOIN",
        "whoCanViewMembership": who_can_view_membership,
        "whoCanViewGroup": who_can_view_group,
        "allowExternalMembers": "true",  # can't be tighter until we start forcing people to use @iwe addresses
        "whoCanPostMessage": who_can_post_message,
        "allowWebPosting": "true",
        "primaryLanguage": "en",
        "isArchived": ("true" if mmcfg["archive"] else "false"),
        "archiveOnly": "false",
        "messageModerationLevel": message_moderation_level,
        "spamModerationLevel": "MODERATE",  # this is the default
        "replyTo": "REPLY_TO_IGNORE",  # users individually decide where the message reply is sent
        # "customReplyTo": "",  # only if replyTo is REPLY_TO_CUSTOM
        "includeCustomFooter": "false",
        # "customFooterText": ""  # only if includeCustomFooter,
        "sendMessageDenyNotification": "false",
        # "defaultMessageDenyNotificationText": "",  # only matters if sendMessageDenyNotification is true
        "membersCanPostAsTheGroup": "false",
        "includeInGlobalAddressList": "false",  # has to do with Outlook integration
        "whoCanLeaveGroup": ("ALL_MEMBERS_CAN_LEAVE" if mmcfg["unsubscribe_policy"] else "NONE_CAN_LEAVE"),
        "whoCanContactOwner": "ALL_IN_DOMAIN_CAN_CONTACT",
        "favoriteRepliesOnTop": "false",
        "whoCanApproveMembers": "ALL_MANAGERS_CAN_APPROVE",
        "whoCanBanUsers": "OWNERS_AND_MANAGERS",
        "whoCanModerateMembers": "OWNERS_AND_MANAGERS",
        "whoCanModerateContent": "OWNERS_AND_MANAGERS",
        "whoCanAssistContent": "NONE",  # has something to do with collaborative inbox
        "enableCollaborativeInbox": "false",
        "whoCanDiscoverGroup": (
            "ALL_IN_DOMAIN_CAN_DISCOVER" if mmcfg["advertised"] else "ALL_MEMBERS_CAN_DISCOVER"
        ),
        "defaultSender": "DEFAULT_SELF",
    }
    return ggcfg


def main():
    parser = argparse.ArgumentParser(
        description="Import mailman list configuration (only settings) created\n"
        "by `pickle-mailman-list.py` into Google Groups using Google API¹.",
        epilog="Notes:\n"
        "[1] The following APIs must be enabled: Admin SDK, Group Settings.\n"
        "[2] The service account needs to be set up for domain-wide delegation.\n"
        "[3] The delegate account needs to have a Google Workspace admin role.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--mailman-pickle",
        metavar="PATH",
        required=True,
        help="mailman list configuration pickle created by pickle-mailman-list.py",
    )
    parser.add_argument(
        "--controlled-mailing-list",
        action="store_true",
        help="override Google group settings to be compatible with the controlled mailing list paradigm",
    )
    parser.add_argument(
        "--sa-creds",
        metavar="PATH",
        required=True,
        help="service account credentials JSON²",
    )
    parser.add_argument(
        "--sa-delegate",
        metavar="EMAIL",
        required=True,
        help="the principal whom the service account will impersonate³",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="logging level (default: info)",
    )
    parser.add_argument(
        "--browser-google-account-index",
        metavar="NUM",
        type=int,
        default=0,
        help="index of the account in your browser's list of Google accounts that\n"
        "has permission to edit settings of the group that will be created.\n"
        "This is purely for convenience: group management URL will print out\n"
        "like https://groups.google.com/u/NUM/... (default: 0)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)s %(message)s",
    )

    logging.info(f"Retrieving mailman list configuration from {args.mailman_pickle}")
    with open(args.mailman_pickle, "rb") as f:
        mmcfg = pickle.load(f)

    logging.debug(pformat(mmcfg))
    logging.info("Converting mailman list settings to google group settings")
    ggcfg = get_google_group_config_from_mailman_config(mmcfg)
    logging.debug(pformat(ggcfg))

    if args.controlled_mailing_list:
        if ggcfg["whoCanJoin"] != "INVITED_CAN_JOIN":
            logging.warning("Overriding whoCanJoin to be 'INVITED_CAN_JOIN'")
            ggcfg["whoCanJoin"] = "INVITED_CAN_JOIN"
        # XXX
        if ggcfg["whoCanViewGroup"] != "ALL_MEMBERS_CAN_VIEW":
            logging.warning("Overriding whoCanViewGroup to be 'ALL_MEMBERS_CAN_VIEW'")
            ggcfg["whoCanViewGroup"] = "ALL_MEMBERS_CAN_VIEW"
        if ggcfg["allowExternalMembers"] != "false":
            logging.warning("Overriding allowExternalMembers to be 'false'")
            ggcfg["allowExternalMembers"] = "false"
        if ggcfg["whoCanLeaveGroup"] != "NONE_CAN_LEAVE":
            logging.warning("Overriding whoCanLeaveGroup to be 'NONE_CAN_LEAVE'")
            ggcfg["whoCanLeaveGroup"] = "NONE_CAN_LEAVE"

    logging.info(f"whoCanViewGroup = {ggcfg['whoCanViewGroup']}")
    logging.info(f"whoCanViewMembership = {ggcfg['whoCanViewMembership']}")
    logging.info(f"allowExternalMembers = {ggcfg['allowExternalMembers']}")
    logging.info(f"whoCanPostMessage = {ggcfg['whoCanPostMessage']}")
    logging.info(f"messageModerationLevel = {ggcfg['messageModerationLevel']}")
    logging.info(f"whoCanDiscoverGroup = {ggcfg['whoCanDiscoverGroup']}")
    if (
        ggcfg["whoCanPostMessage"] == "ANYONE_CAN_POST"
        and ggcfg["messageModerationLevel"] == "MODERATE_NONE"
        and ggcfg["allowExternalMembers"] == "true"
    ):
        logging.warning(f"!!!  LIST ACCEPTS MESSAGES FROM ANYBODY WITHOUT MODERATION")

    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.group.member",
        "https://www.googleapis.com/auth/apps.groups.settings",
    ]

    creds = service_account.Credentials.from_service_account_file(
        args.sa_creds, scopes=SCOPES, subject=args.sa_delegate
    )

    svc = discovery.build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    try:
        logging.info(f"Creating group {ggcfg['email']}")
        svc.groups().insert(
            body={
                "description": ggcfg["description"],
                "email": ggcfg["email"],
                "name": ggcfg["name"],
            }
        ).execute()
    except HttpError as e:
        if e.status_code == 409:  # entity already exists
            logging.info("Group already exists")
        else:
            raise
    finally:
        svc.close()

    svc = discovery.build("groupssettings", "v1", credentials=creds, cache_discovery=False)
    try:
        logging.info(f"Configuring group {ggcfg['email']}")
        svc.groups().patch(
            groupUniqueId=ggcfg["email"],
            body=ggcfg,
        ).execute()
    finally:
        svc.close()

    logging.warning("!!!   SOME GOOGLE GROUP OPTIONS CANNOT BE SET PROGRAMMATICALLY")
    addr, domain = ggcfg["email"].split("@")
    logging.warning(
        f"!!!   Set 'Subject prefix' to '{mmcfg['subject_prefix'].strip()}' in the 'Email options' section"
    )
    logging.warning(
        f"!!!   Consider enabling 'Include the standard Groups footer' in the 'Email options' section"
    )
    logging.warning(
        f"!!!   https://groups.google.com/u/{args.browser_google_account_index}/a/{domain}/g/{addr}/settings#email"
    )


if __name__ == "__main__":
    sys.exit(main())