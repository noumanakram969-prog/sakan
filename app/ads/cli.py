"""Command line for the ads layer.

    python -m app.ads.cli check
    python -m app.ads.cli build-campaign --name "JVC buyers - Oct"
    python -m app.ads.cli report --days 7
    python -m app.ads.cli rules --target-cpl 50
    python -m app.ads.cli send-event --phone +971588129679

Writes go to the sandbox account when one is configured, and every object is
created PAUSED. `rules` is a dry run unless --apply is passed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import (
    CampaignBuilder,
    ConversionsAPI,
    GraphClient,
    MetaError,
    RuleSet,
    Targeting,
    apply,
    evaluate,
    fetch,
    render,
    settings_from_env,
    summarise,
)


def _client(cfg) -> GraphClient:
    if not cfg.access_token:
        sys.exit("No META_ADS_ACCESS_TOKEN. Fill .env.ads first.")
    return GraphClient(cfg.access_token, version=cfg.graph_version)


def cmd_check(args, cfg) -> int:
    """Prove the credentials work before anything is built on them."""
    with _client(cfg) as c:
        tok = c.get("debug_token", input_token=cfg.access_token).get("data", {})
        print(f"token    : valid={tok.get('is_valid')} app={tok.get('application')}")
        print(f"scopes   : {', '.join(tok.get('scopes', [])) or '(none)'}")

        for label, acct in (("write ", cfg.write_account), ("read  ", cfg.ad_account_id)):
            if not acct:
                continue
            try:
                a = c.get(acct, fields="name,account_status,currency,timezone_name")
                print(f"{label}   : {a.get('id')} {a.get('name')!r} "
                      f"status={a.get('account_status')} {a.get('currency')}")
            except MetaError as e:
                print(f"{label}   : {acct} UNREACHABLE - {e.message}")

        if cfg.page_id:
            try:
                p = c.get(cfg.page_id, fields="name")
                print(f"page     : {p.get('id')} {p.get('name')!r}")
            except MetaError as e:
                print(f"page     : {cfg.page_id} UNREACHABLE - {e.message}")

        print(f"pixel    : {cfg.pixel_id or '(not set)'}"
              f"{'  [test events only]' if cfg.capi_test_event_code else ''}")
    return 0


def cmd_build_campaign(args, cfg) -> int:
    """Campaign -> ad set -> two creative variants. All PAUSED."""
    with _client(cfg) as c:
        b = CampaignBuilder(c, cfg.write_account, page_id=cfg.page_id)

        campaign_id = b.create_campaign(args.name, objective=args.objective)
        print(f"campaign : {campaign_id}  PAUSED")

        ad_set_id = b.create_ad_set(
            campaign_id,
            f"{args.name} - {args.country}",
            daily_budget_minor=args.budget,
            targeting=Targeting(countries=[args.country], age_min=args.age_min, age_max=args.age_max),
            destination_type=args.destination,
        )
        print(f"ad set   : {ad_set_id}  PAUSED  budget={args.budget} minor units")

        if cfg.page_id:
            variants = [
                {"label": "price", "message": "Studios in JVC from AED 650,000. Payment plan over 3 years.",
                 "headline": "JVC studios, real prices"},
                {"label": "data", "message": "Every JVC project, filed handover dates from the DLD register.",
                 "headline": "JVC: what the register says"},
            ]
            ads = b.create_creative_test(ad_set_id, variants, link=args.link, name_prefix=args.name[:20])
            for a in ads:
                print(f"ad       : {a['ad_id']}  variant={a['label']}  PAUSED")
        else:
            print("ad       : skipped, no META_PAGE_ID")

        print("\nNothing is running. Activate deliberately in Ads Manager, or with set_status.")
    return 0


def cmd_report(args, cfg) -> int:
    account = args.account or cfg.ad_account_id or cfg.write_account
    with _client(cfg) as c:
        rows = fetch(c, account, level=args.level, date_preset=f"last_{args.days}d")
        if args.json:
            print(json.dumps({"summary": summarise(rows), "rows": [r.as_dict() for r in rows]}, indent=2))
        else:
            print(render(rows))
    return 0


def cmd_rules(args, cfg) -> int:
    account = args.account or cfg.ad_account_id or cfg.write_account
    rules = RuleSet(target_cost_per_lead=args.target_cpl)

    with _client(cfg) as c:
        rows = fetch(c, account, level="adset", date_preset=f"last_{args.days}d")

        budgets: dict[str, int] = {}
        for r in rows:
            try:
                budgets[r.object_id] = int(c.get(r.object_id, fields="daily_budget").get("daily_budget", 0))
            except MetaError:
                continue

        actions = evaluate(rows, budgets, rules)
        if not actions:
            print("No changes proposed.")
            return 0

        print(f"{len(actions)} proposed change(s), target CPL {args.target_cpl:.2f}:\n")
        for a in actions:
            print(" ", a)

        b = CampaignBuilder(c, account, page_id=cfg.page_id)
        results = apply(b, actions, dry_run=not args.apply)
        print(f"\n{'APPLIED' if args.apply else 'DRY RUN - nothing changed'} ({len(results)})")
    return 0


def cmd_send_event(args, cfg) -> int:
    if not cfg.pixel_id:
        sys.exit("No META_PIXEL_ID in .env.ads")

    token = cfg.capi_token or cfg.access_token
    with GraphClient(token, version=cfg.graph_version) as c:
        capi = ConversionsAPI(c, cfg.pixel_id, test_event_code=cfg.capi_test_event_code or None)
        if args.event == "lead":
            res = capi.lead(phone=args.phone, email=args.email, source=args.source)
        else:
            res = capi.booking(phone=args.phone, value=args.value, service=args.service)
        print(json.dumps(res, indent=2))
        if cfg.capi_test_event_code:
            print("\nSent as a TEST event - visible in Events Manager > Test Events, "
                  "not in reporting.")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    p = argparse.ArgumentParser(prog="app.ads.cli", description="Meta ads automation")
    p.add_argument("--env", default=".env.ads")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="verify token, accounts and page")

    b = sub.add_parser("build-campaign", help="create a PAUSED campaign with a creative test")
    b.add_argument("--name", default="Mistri test campaign")
    b.add_argument("--objective", default="OUTCOME_LEADS")
    b.add_argument("--budget", type=int, default=5000, help="daily budget in minor units (5000 = AED 50)")
    b.add_argument("--country", default="AE")
    b.add_argument("--age-min", type=int, default=25)
    b.add_argument("--age-max", type=int, default=60)
    b.add_argument("--destination", default=None, help="e.g. WHATSAPP")
    b.add_argument("--link", default="https://mistri.offpageos.com")

    r = sub.add_parser("report", help="performance report")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--level", default="campaign", choices=["campaign", "adset", "ad"])
    r.add_argument("--account", default=None)
    r.add_argument("--json", action="store_true")

    u = sub.add_parser("rules", help="evaluate budget rules (dry run by default)")
    u.add_argument("--target-cpl", type=float, required=True)
    u.add_argument("--days", type=int, default=7)
    u.add_argument("--account", default=None)
    u.add_argument("--apply", action="store_true", help="actually change budgets")

    e = sub.add_parser("send-event", help="send a Conversions API event")
    e.add_argument("--event", default="lead", choices=["lead", "booking"])
    e.add_argument("--phone", default=None)
    e.add_argument("--email", default=None)
    e.add_argument("--source", default="whatsapp")
    e.add_argument("--value", type=float, default=None)
    e.add_argument("--service", default=None)

    args = p.parse_args(argv)
    cfg = settings_from_env(args.env)

    handlers = {
        "check": cmd_check,
        "build-campaign": cmd_build_campaign,
        "report": cmd_report,
        "rules": cmd_rules,
        "send-event": cmd_send_event,
    }
    try:
        return handlers[args.cmd](args, cfg)
    except MetaError as e:
        print(f"\nMeta API error: {e}", file=sys.stderr)
        if e.user_message:
            print(e.user_message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
