"""Budget rules.

A rule reads yesterday's numbers and proposes a change. Three things keep this
from being dangerous:

1. **Evaluating is separate from applying.** `evaluate` touches nothing; it
   returns a list of proposed Actions. `apply` is a second call. So the same
   code can run in a report, in a dry run, and for real, and the dry run is the
   default everywhere it is wired up.

2. **A minimum sample.** An ad set with 40 impressions has not earned an
   opinion. Acting on noise is the classic way automated budget rules destroy an
   account - they chase whichever variant got lucky before lunch.

3. **Bounded steps.** No rule can move a budget more than a set fraction per
   run, or below the floor, or above a ceiling the owner sets. The worst a bad
   day can do is one step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from .campaigns import MIN_DAILY_BUDGET_MINOR, CampaignBuilder
from .insights import Row

log = logging.getLogger("mistri.ads")

Verb = Literal["increase_budget", "decrease_budget", "pause"]


@dataclass
class Action:
    verb: Verb
    object_id: str
    name: str
    reason: str
    current_budget_minor: int | None = None
    new_budget_minor: int | None = None

    def __str__(self) -> str:
        if self.verb == "pause":
            return f"PAUSE   {self.name} ({self.object_id}) - {self.reason}"
        return (
            f"{'RAISE ' if self.verb == 'increase_budget' else 'LOWER '} "
            f"{self.name} ({self.object_id}) "
            f"{self.current_budget_minor} -> {self.new_budget_minor} - {self.reason}"
        ).replace("  ", " ")


@dataclass
class RuleSet:
    """The thresholds, in one object the owner can actually be shown."""

    target_cost_per_lead: float          # account currency, major units
    min_impressions: int = 1000          # below this, no opinion
    min_spend: float = 20.0              # and no opinion below this either
    good_ratio: float = 0.75             # CPL under 75% of target -> scale up
    bad_ratio: float = 1.50              # CPL over 150% of target -> scale down
    step: float = 0.20                   # never move more than 20% in one run
    max_daily_budget_minor: int = 50_000 # ceiling the owner sets, not the code
    pause_after_spend_no_leads: float = 60.0


def evaluate(rows: list[Row], budgets: dict[str, int], rules: RuleSet) -> list[Action]:
    """Pure. Reads numbers, proposes changes, touches nothing."""
    actions: list[Action] = []

    for r in rows:
        budget = budgets.get(r.object_id)

        # Spent real money and produced nothing. This one fires regardless of
        # the impression floor, because "no leads" is the one conclusion a
        # small sample can still support once the spend is meaningful.
        if r.leads == 0 and r.spend >= rules.pause_after_spend_no_leads:
            actions.append(Action(
                verb="pause",
                object_id=r.object_id,
                name=r.name,
                reason=f"spent {r.spend:.2f} with no leads",
            ))
            continue

        if r.impressions < rules.min_impressions or r.spend < rules.min_spend:
            continue  # not enough to judge

        cpl = r.cost_per_lead
        if cpl is None or budget is None:
            continue

        if cpl <= rules.target_cost_per_lead * rules.good_ratio:
            new = _clamp(int(budget * (1 + rules.step)), rules)
            if new > budget:
                actions.append(Action(
                    "increase_budget", r.object_id, r.name,
                    f"CPL {cpl:.2f} vs target {rules.target_cost_per_lead:.2f}",
                    budget, new,
                ))

        elif cpl >= rules.target_cost_per_lead * rules.bad_ratio:
            new = _clamp(int(budget * (1 - rules.step)), rules)
            if new < budget:
                actions.append(Action(
                    "decrease_budget", r.object_id, r.name,
                    f"CPL {cpl:.2f} vs target {rules.target_cost_per_lead:.2f}",
                    budget, new,
                ))

    return actions


def apply(builder: CampaignBuilder, actions: list[Action], *, dry_run: bool = True) -> list[dict[str, Any]]:
    """Carry out the proposals. dry_run defaults to True on purpose."""
    done = []
    for a in actions:
        if dry_run:
            log.info("DRY RUN %s", a)
            done.append({"action": a.verb, "id": a.object_id, "applied": False})
            continue

        if a.verb == "pause":
            builder.set_status(a.object_id, "PAUSED")
        else:
            assert a.new_budget_minor is not None
            builder.set_daily_budget(a.object_id, a.new_budget_minor)

        log.info("APPLIED %s", a)
        done.append({"action": a.verb, "id": a.object_id, "applied": True,
                     "new_budget_minor": a.new_budget_minor})
    return done


def _clamp(minor: int, rules: RuleSet) -> int:
    return max(MIN_DAILY_BUDGET_MINOR, min(minor, rules.max_daily_budget_minor))
