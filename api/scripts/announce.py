#!/usr/bin/env python3
"""Announce a new tool (or major update) to every active subscriber, with a per-recipient one-click unsubscribe link.

Usage (from api/ with the venv and AWS_PROFILE set):
  AWS_PROFILE=podsite-aws-profile .venv/bin/python scripts/announce.py \
      --subject "New free tool: Opening Hours Checker" --body announce.txt [--dry-run] [--only maker@example.com]

The body file is plain text; the string {unsubscribe} is replaced per recipient (added at the end if missing).
Reads ORIGIN_VERIFY_SECRET / UNSUBSCRIBE_SECRET from api/.env so the links match the deployed API.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.notify import _html, unsubscribe_url  # noqa: E402

TABLE = os.environ.get("QUOTA_TABLE", "locan-api")
REGION = os.environ.get("AWS_REGION", "us-west-2")
SENDER = os.environ.get("ALERT_FROM", "alerts@locan.ai")
API_BASE = os.environ.get("API_BASE_URL", "https://api.locan.ai/api")


def load_env() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def active_subscribers(table) -> list[str]:
    emails: list[str] = []
    kwargs = {"FilterExpression": "begins_with(PK, :p) AND #s = :a", "ExpressionAttributeNames": {"#s": "status"},
              "ExpressionAttributeValues": {":p": "SUB#", ":a": "active"}}
    while True:
        page = table.scan(**kwargs)
        emails += [i["email"] for i in page.get("Items", []) if i.get("email")]
        if "LastEvaluatedKey" not in page:
            return sorted(set(e.lower() for e in emails))
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True, help="plain-text file; {unsubscribe} placeholder optional")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="send to this single address (test)")
    args = ap.parse_args()

    secret = os.environ.get("UNSUBSCRIBE_SECRET") or os.environ.get("ORIGIN_VERIFY_SECRET")
    if not secret:
        print("UNSUBSCRIBE_SECRET/ORIGIN_VERIFY_SECRET missing (api/.env)", file=sys.stderr)
        return 2
    body = Path(args.body).read_text()
    if "{unsubscribe}" not in body:
        body = body.rstrip() + "\n\nUnsubscribe with one click: {unsubscribe}\n"

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    recipients = [args.only] if args.only else active_subscribers(table)
    print(f"{len(recipients)} recipient(s){' (dry run)' if args.dry_run else ''}")
    ses = boto3.client("sesv2", region_name=REGION)
    sent = 0
    for email in recipients:
        text = body.replace("{unsubscribe}", unsubscribe_url(API_BASE, secret, email))
        if args.dry_run:
            print(f"  would send to {email}")
            continue
        ses.send_email(
            FromEmailAddress=SENDER,
            Destination={"ToAddresses": [email]},
            Content={"Simple": {"Subject": {"Data": args.subject}, "Body": {"Text": {"Data": text}, "Html": {"Data": _html(text)}}}},
        )
        sent += 1
        time.sleep(0.1)  # stay well under the SES send rate
    print(f"sent {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
