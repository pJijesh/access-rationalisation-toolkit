"""Seeded generator for a synthetic, deliberately messy access model.

Everything here is invented. Permission names follow a generic `module.action`
convention and do not correspond to any real product. Users are anonymous ids.
The structure imitates a mid-sized freight-forwarding style business: operations,
customs, finance, sales, warehouse, administration and management.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

# department -> [(job title, headcount)]
DEPARTMENTS: dict[str, list[tuple[str, int]]] = {
    "Operations": [
        ("Freight Operator", 20),
        ("Senior Freight Operator", 8),
        ("Customer Service Agent", 6),
        ("Operations Supervisor", 3),
        ("Operations Manager", 1),
    ],
    "Customs": [
        ("Customs Clerk", 12),
        ("Senior Customs Clerk", 6),
        ("Customs Supervisor", 3),
        ("Customs Compliance Lead", 1),
    ],
    "Finance": [
        ("Accounts Payable Clerk", 5),
        ("Accounts Receivable Clerk", 5),
        ("Credit Controller", 2),
        ("Accountant", 3),
        ("Treasury Analyst", 1),
        ("Finance Manager", 2),
    ],
    "Sales": [
        ("Account Executive", 11),
        ("Sales Coordinator", 8),
        ("Pricing Analyst", 2),
        ("Sales Manager", 3),
        ("Business Development Manager", 2),
    ],
    "Warehouse": [
        ("Warehouse Operative", 17),
        ("Goods In Clerk", 6),
        ("Stock Controller", 3),
        ("Warehouse Supervisor", 3),
        ("Warehouse Manager", 1),
    ],
    "Administration": [
        ("IT Support Analyst", 2),
        ("HR Administrator", 2),
        ("Office Administrator", 3),
        ("Systems Administrator", 1),
    ],
    "Management": [
        ("Director", 4),
        ("Compliance Officer", 1),
        ("Head of Department", 3),
    ],
}


def P(*names: str) -> frozenset[str]:
    return frozenset(names)


ALL_STAFF = P("document.view", "tracking.view")
OPS_BASIC = P("shipment.view", "booking.view", "tracking.view", "document.view", "customer.view")
OPS_BOOK = OPS_BASIC | P(
    "booking.create", "booking.edit", "booking.confirm", "shipment.create", "shipment.edit",
    "tracking.update", "document.upload",
)
OPS_SENIOR = OPS_BOOK | P("shipment.cancel", "shipment.close")
CUS_BASIC = P("customs.view", "tariff.view", "shipment.view", "document.view")
CUS_DRAFT = CUS_BASIC | P("customs.draft", "customs.amend", "document.upload")
CUS_SUBMIT = CUS_DRAFT | P("customs.submit")
FIN_AP = P("invoice.view", "invoice.create", "invoice.edit", "supplier.view", "payment.view", "payment.create", "ledger.view")
FIN_AR = P("invoice.view", "invoice.create", "invoice.edit", "customer.view", "ledger.view")
SAL_BASIC = P("customer.view", "quote.view", "shipment.view", "tracking.view", "rate.view")
SAL_QUOTE = SAL_BASIC | P("quote.create", "quote.edit", "customer.create", "customer.edit")
WH_BASIC = P("stock.view", "shipment.view", "tracking.view")
WH_OPERATIVE = WH_BASIC | P("stock.receive", "stock.pick", "stock.dispatch", "tracking.update")

# Each legacy group: (name, permissions, [(department, job title or "*", probability)]).
# Names deliberately mix conventions, as real estates do after years of change.
GROUPS: list[tuple[str, frozenset[str], list[tuple[str, str, float]]]] = [
    ("ALL_STAFF", ALL_STAFF, [("*", "*", 0.96)]),
    ("SHARED_MAILBOX_LEGACY", P(), [("Administration", "Office Administrator", 0.7), ("Sales", "Sales Coordinator", 0.2), ("Operations", "Customer Service Agent", 0.3)]),
    # Operations
    ("OPS_BASIC", OPS_BASIC, [("Operations", "*", 0.9)]),
    ("OPS_BOOKING", OPS_BOOK, [("Operations", "Freight Operator", 0.75), ("Operations", "Senior Freight Operator", 0.8), ("Operations", "Customer Service Agent", 0.2)]),
    ("OPS_BOOKING_COPY", OPS_BOOK, [("Operations", "Freight Operator", 0.2), ("Operations", "Senior Freight Operator", 0.15)]),
    ("OPS_BOOKING_V2", OPS_BOOK | P("document.delete"), [("Operations", "Senior Freight Operator", 0.35), ("Operations", "Operations Supervisor", 0.5)]),
    ("OPS_SENIOR", OPS_SENIOR, [("Operations", "Senior Freight Operator", 0.7), ("Operations", "Operations Supervisor", 1.0)]),
    ("OPS_SUPERVISOR", OPS_SENIOR | P("rate.view", "quote.view", "report.view"), [("Operations", "Operations Supervisor", 1.0), ("Operations", "Operations Manager", 1.0)]),
    ("OPS_CSA", OPS_BASIC | P("tracking.update", "document.upload", "quote.view"), [("Operations", "Customer Service Agent", 0.95)]),
    ("OPS_TRIAL_OLD", OPS_BOOK, []),
    # Customs
    ("CUS_BASIC", CUS_BASIC, [("Customs", "*", 0.9)]),
    ("CUS_DRAFT", CUS_DRAFT, [("Customs", "Customs Clerk", 0.8), ("Customs", "Senior Customs Clerk", 0.6)]),
    ("CUS_DRAFT_TEMP", CUS_DRAFT, [("Customs", "Customs Clerk", 0.2)]),
    ("CUS_SUBMIT", CUS_SUBMIT, [("Customs", "Senior Customs Clerk", 0.85), ("Customs", "Customs Clerk", 0.1)]),
    ("CUS_SUBMIT_V2", CUS_SUBMIT | P("document.delete"), [("Customs", "Senior Customs Clerk", 0.3), ("Customs", "Customs Supervisor", 0.5)]),
    ("CUS_APPROVE", P("customs.view", "customs.approve", "document.view", "report.view"), [("Customs", "Customs Supervisor", 1.0), ("Customs", "Customs Compliance Lead", 1.0)]),
    ("CUS_PROJECT_TEMP", CUS_DRAFT | P("customs.submit"), []),
    # Finance
    ("FIN_AP", FIN_AP, [("Finance", "Accounts Payable Clerk", 1.0), ("Finance", "Accountant", 0.3)]),
    ("FIN_AP_APPROVE", P("invoice.view", "invoice.approve", "payment.view", "payment.approve", "supplier.view"), [("Finance", "Finance Manager", 1.0), ("Finance", "Accountant", 0.5)]),
    ("FIN_AR", FIN_AR, [("Finance", "Accounts Receivable Clerk", 1.0), ("Finance", "Credit Controller", 1.0)]),
    ("FIN_AR_V2", FIN_AR | P("customer.set_credit_limit"), [("Finance", "Credit Controller", 0.5), ("Finance", "Finance Manager", 1.0)]),
    ("FIN_TREASURY", P("payment.view", "payment.release", "supplier.view", "ledger.view"), [("Finance", "Treasury Analyst", 1.0), ("Finance", "Finance Manager", 0.5)]),
    ("FIN_SUPPLIER_MASTER", P("supplier.view", "supplier.create", "supplier.edit", "supplier.edit_bank_details"), [("Finance", "Accounts Payable Clerk", 0.2), ("Finance", "Accountant", 0.3)]),
    ("FIN_REPORTING", P("report.view", "report.export", "report.financial", "ledger.view", "invoice.view"), [("Finance", "Accountant", 1.0), ("Finance", "Finance Manager", 1.0), ("Finance", "Credit Controller", 0.5)]),
    ("FIN_YEAREND_OLD", P("ledger.view", "ledger.post", "ledger.adjust", "report.financial"), []),
    # Sales
    ("SAL_BASIC", SAL_BASIC, [("Sales", "*", 0.95)]),
    ("SAL_QUOTE", SAL_QUOTE, [("Sales", "Account Executive", 0.8), ("Sales", "Sales Coordinator", 0.5), ("Sales", "Business Development Manager", 1.0), ("Sales", "Sales Manager", 1.0)]),
    ("SAL_QUOTING", SAL_QUOTE, [("Sales", "Account Executive", 0.2), ("Sales", "Sales Coordinator", 0.3)]),
    ("SAL_MANAGER", SAL_QUOTE | P("quote.approve", "report.view", "report.export"), [("Sales", "Sales Manager", 1.0)]),
    ("SAL_PRICING", P("rate.view", "rate.edit", "quote.view"), [("Sales", "Pricing Analyst", 1.0), ("Sales", "Sales Manager", 0.3)]),
    ("SAL_QUOTE_APPROVE", P("quote.view", "quote.approve", "customer.view", "report.view"), [("Sales", "Sales Manager", 1.0), ("Sales", "Business Development Manager", 0.5)]),
    # Warehouse
    ("WH_BASIC", WH_BASIC, [("Warehouse", "*", 0.95)]),
    ("WH_OPERATIVE", WH_OPERATIVE, [("Warehouse", "Warehouse Operative", 0.85), ("Warehouse", "Goods In Clerk", 0.3), ("Warehouse", "Stock Controller", 0.5)]),
    ("WH_OPERATIVE_OLD", WH_OPERATIVE - P("stock.dispatch"), [("Warehouse", "Warehouse Operative", 0.2)]),
    ("WH_GOODS_IN", P("stock.view", "stock.receive", "document.upload", "shipment.view"), [("Warehouse", "Goods In Clerk", 0.95)]),
    ("WH_SUPERVISOR", WH_OPERATIVE | P("stock.adjust", "location.edit", "report.view"), [("Warehouse", "Warehouse Supervisor", 1.0), ("Warehouse", "Warehouse Manager", 1.0), ("Warehouse", "Stock Controller", 0.6)]),
    ("WH_ADJUST_APPROVE", P("stock.view", "stock.approve_adjustment", "report.view"), [("Warehouse", "Warehouse Manager", 1.0), ("Warehouse", "Warehouse Supervisor", 0.3)]),
    # Administration and management
    ("ADM_USERS", P("user.view", "user.create", "user.reset_password"), [("Administration", "IT Support Analyst", 1.0), ("Administration", "HR Administrator", 0.5)]),
    ("ADM_CONFIG", P("config.view", "config.edit"), [("Administration", "Systems Administrator", 1.0), ("Administration", "IT Support Analyst", 0.5)]),
    ("SYS_ADMIN", P("user.view", "user.create", "user.reset_password", "user.admin", "config.view", "config.edit", "config.admin", "audit.view"), [("Administration", "Systems Administrator", 1.0)]),
    ("MGT_DASHBOARD", P("report.view", "report.export", "report.financial", "shipment.view", "invoice.view", "customer.view"), [("Management", "Director", 1.0), ("Management", "Head of Department", 1.0)]),
    ("AUDIT_READONLY", P("audit.view", "report.audit", "report.view", "ledger.view", "user.view"), [("Management", "Compliance Officer", 1.0), ("Management", "Director", 0.5)]),
]

SOD_RULES: list[tuple[str, str, str, str]] = [
    ("SOD-001", "supplier.create", "payment.approve", "Create a supplier and approve payments"),
    ("SOD-002", "invoice.create", "invoice.approve", "Raise and approve the same invoice"),
    ("SOD-003", "payment.create", "payment.approve", "Prepare and approve a payment"),
    ("SOD-004", "supplier.edit_bank_details", "payment.release", "Change bank details and release payments"),
    ("SOD-005", "customs.submit", "customs.approve", "Submit and approve a customs entry"),
    ("SOD-006", "rate.edit", "quote.approve", "Set rates and approve quotes"),
    ("SOD-007", "stock.adjust", "stock.approve_adjustment", "Adjust stock and approve the adjustment"),
    ("SOD-008", "config.admin", "audit.view", "Administer the system and review its audit trail"),
]

# Extra memberships planted on purpose: (candidate title, extra group, how many users)
PLANTED_CONFLICTS: list[tuple[str, str, int]] = [
    ("Accounts Payable Clerk", "FIN_AP_APPROVE", 2),
    ("Accountant", "FIN_TREASURY", 1),
    ("Senior Customs Clerk", "CUS_APPROVE", 2),
    ("Stock Controller", "WH_ADJUST_APPROVE", 1),
    ("Pricing Analyst", "SAL_QUOTE_APPROVE", 1),
]

CREEP_POOL = ["OPS_BASIC", "SAL_BASIC", "WH_BASIC", "CUS_BASIC"]


def build_demo(seed: int = 42) -> dict[str, list[list[str]]]:
    """Return the demo dataset as CSV rows (header first), deterministic for a seed."""
    rng = random.Random(seed)

    users: list[tuple[str, str, str]] = []
    n = 0
    for dept, titles in DEPARTMENTS.items():
        for title, count in titles:
            for _ in range(count):
                n += 1
                users.append((f"U{n:03d}", dept, title))

    perms_by_group = {name: perms for name, perms, _rules in GROUPS}
    memberships: set[tuple[str, str]] = set()
    for name, _perms, rules in GROUPS:
        before = len(memberships)
        for user, dept, title in users:
            for rule_dept, rule_title, prob in rules:
                if rule_dept in ("*", dept) and rule_title in ("*", title):
                    if rng.random() < prob:
                        memberships.add((user, name))
                    break
        if rules and len(memberships) == before:  # never leave a live group empty
            for user, dept, title in users:
                if any(rd in ("*", dept) and rt in ("*", title) for rd, rt, _p in rules):
                    memberships.add((user, name))
                    break

    # Planted separation-of-duties problems.
    for title, group, how_many in PLANTED_CONFLICTS:
        candidates = [u for u, _d, t in users if t == title]
        for user in rng.sample(candidates, min(how_many, len(candidates))):
            memberships.add((user, group))

    # Access creep: a few people carry an extra basic group from another department.
    for user, _dept, _title in users:
        if rng.random() < 0.05:
            memberships.add((user, rng.choice(CREEP_POOL)))

    return {
        "users.csv": [["user", "department", "job_title"], *[list(u) for u in users]],
        "memberships.csv": [["user", "group"], *[list(m) for m in sorted(memberships)]],
        "group_permissions.csv": [
            ["group", "permission"],
            *[[g, p] for g in sorted(perms_by_group) for p in sorted(perms_by_group[g])],
        ],
        "sod_rules.csv": [["rule_id", "permission_a", "permission_b", "description"], *[list(r) for r in SOD_RULES]],
    }


def write_demo(out_dir: Path | str, seed: int = 42) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, rows in build_demo(seed).items():
        path = out / name
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh, lineterminator="\n").writerows(rows)
        written[name] = path
    return written
