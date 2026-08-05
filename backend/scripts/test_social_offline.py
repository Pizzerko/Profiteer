"""Offline verification for the social layer: following, privacy, the feed, and competitions.

Runs against an in-memory SQLite DB and a fake, always-REGULAR market data provider, so it works
with the market closed. Route handlers are invoked as plain functions (their `Depends(...)` defaults
are passed explicitly) — that exercises the real guard code without needing an HTTP server.

Run:  ./.venv/Scripts/python.exe scripts/test_social_offline.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Run directly from backend/ (`python scripts/test_social_offline.py`): Python puts *this* file's
# directory on sys.path, not backend/, so `app` wouldn't import without this.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.services.market_data as market_data
from app.api.routes.competitions import (
    create_competition,
    delete_competition,
    join_competition,
    leave_competition,
    list_competitions,
)
from app.api.routes.competitions import competition_standings as standings_route
from app.api.routes.portfolio import reset_portfolio
from app.api.routes.portfolios import delete_portfolio, list_portfolios
from app.api.routes.users import follow, profile, search, unfollow, update_me
from app.db.base import Base
from app.models.competition import Competition
from app.models.follow import Follow
from app.models.option_trade import OptionTrade
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.models.order import Order
from app.models.user import User
from app.schemas.market import OptionContract, Quote
from app.schemas.portfolio import OptionOrderRequest
from app.schemas.social import CompetitionCreate, ProfileUpdate
from app.services.competitions import (
    ACTIVE,
    ENDED,
    UPCOMING,
    competition_status,
    finalize_ended_competitions,
)
from app.services.options import place_option_order
from app.services.social import build_feed, build_public_profile, public_portfolio_of
from app.services.trading import TradingError, execute_trade

# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------
class FakeProvider:
    def __init__(self) -> None:
        self.market_state = "REGULAR"
        self.spot: dict[str, float] = {"AAPL": 200.0, "MSFT": 400.0}
        self.prev_close: dict[str, float] = {}
        self.marks: dict[str, float] = {}                     # occ -> mark per share
        self.meta: dict[str, tuple[str, float]] = {}          # occ -> (option_type, strike)

    def add_contract(self, occ: str, option_type: str, strike: float, mark: float) -> None:
        self.marks[occ] = mark
        self.meta[occ] = (option_type, strike)

    def get_quote(self, symbol: str) -> Quote:
        s = symbol.upper()
        p = self.spot.get(s, 100.0)
        return Quote(
            symbol=s,
            price=p,
            effective_price=p,
            previous_close=self.prev_close.get(s, p),
            market_state=self.market_state,
        )

    def get_option_contract(self, underlying, expiration, option_type, strike):
        for occ, (otype, k) in self.meta.items():
            if otype == option_type and abs(k - strike) < 1e-6:
                m = self.marks[occ]
                return OptionContract(
                    occ_symbol=occ, option_type=otype, strike=k,
                    mark=m, bid=m, ask=m, last_price=m,
                )
        return None

    def get_option_expirations(self, symbol):
        return []

    def get_option_chain(self, symbol, expiration=None):
        raise NotImplementedError


fake = FakeProvider()
market_data._provider = fake  # patch singleton


# ---------------------------------------------------------------------------
# Fixtures & assertions
# ---------------------------------------------------------------------------
def fresh_db():
    """A brand-new in-memory engine per scenario → full isolation."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def mk_user(db, username: str, cash: float = 100_000.0, publish: bool = True):
    """A user with one starter portfolio, published by default (mirrors signup)."""
    u = User(email=f"{username}@example.com", username=username, hashed_password="x")
    db.add(u)
    db.flush()
    p = Portfolio(user_id=u.id, name="Default", cash_balance=cash, starting_balance=cash)
    db.add(p)
    db.flush()
    if publish:
        u.public_portfolio_id = p.id
    db.commit()
    return u, p


def mk_competition(db, creator, starts_in: int, ends_in: int, cash: float = 50_000.0,
                   name: str = "Contest") -> Competition:
    """Competition whose window is [now+starts_in, now+ends_in] minutes (negatives = past)."""
    now = datetime.now(timezone.utc)
    c = Competition(
        name=name, description=None, creator_id=creator.id, starting_cash=cash,
        starts_at=now + timedelta(minutes=starts_in),
        ends_at=now + timedelta(minutes=ends_in),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def entry_of(db, comp: Competition, user: User) -> Portfolio:
    db.refresh(comp)
    return next(e for e in comp.entries if e.user_id == user.id)


passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def expect_trading_error(name: str, fn, contains: str | None = None) -> None:
    global passed, failed
    try:
        fn()
        failed += 1
        print(f"  FAIL  {name}  (expected TradingError, none raised)")
    except TradingError as exc:
        if contains and contains.lower() not in str(exc).lower():
            failed += 1
            print(f"  FAIL  {name}  (message lacked {contains!r}: {exc})")
        else:
            passed += 1
            print(f"  PASS  {name}  -> rejected: {exc}")


def expect_http(name: str, fn, status: int | None = None) -> None:
    global passed, failed
    try:
        fn()
        failed += 1
        print(f"  FAIL  {name}  (expected HTTPException, none raised)")
    except HTTPException as exc:
        if status is not None and exc.status_code != status:
            failed += 1
            print(f"  FAIL  {name}  (expected {status}, got {exc.status_code}: {exc.detail})")
        else:
            passed += 1
            print(f"  PASS  {name}  -> {exc.status_code}: {exc.detail}")


FUTURE_EXP = (date.today() + timedelta(days=30)).isoformat()


# ===========================================================================
print("\n[1] Follow rules")
db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
bob, bob_pf = mk_user(db, "bob")

out = follow("bob", db, alice)
check("follow creates the edge", db.query(Follow).count() == 1)
check("follower_count reflects it", out.follower_count == 1, f"got {out.follower_count}")
check("is_following true for the follower", out.is_following is True)
check("is_me false for someone else", out.is_me is False)

follow("bob", db, alice)  # again
check("following twice is idempotent", db.query(Follow).count() == 1)

expect_http("self-follow rejected", lambda: follow("alice", db, alice), status=400)
expect_http("following an unknown user 404s", lambda: follow("nobody", db, alice), status=404)

me = profile("alice", db, alice)
check("own profile marks is_me", me.is_me is True)
check("own profile following_count = 1", me.following_count == 1, f"got {me.following_count}")

back = unfollow("bob", db, alice)
check("unfollow removes the edge", db.query(Follow).count() == 0)
check("is_following false after unfollow", back.is_following is False)
unfollow("bob", db, alice)  # again
check("unfollowing twice is a no-op", db.query(Follow).count() == 0)
db.close()

# ===========================================================================
print("\n[2] User search")
db = fresh_db()
alice, _ = mk_user(db, "alice")
bob, _ = mk_user(db, "bob")
bob.display_name = "Bobby Tables"
db.commit()
mk_user(db, "carol")

check("matches by username prefix", [u.username for u in search("bo", db, alice)] == ["bob"])
check("matches by display name, case-insensitively",
      [u.username for u in search("bobby t", db, alice)] == ["bob"])
check("excludes the searcher", all(u.username != "alice" for u in search("a", db, alice)))
check("no match → empty list", search("zzzz", db, alice) == [])
db.close()

# ===========================================================================
print("\n[3] Public profile projection withholds private data")
db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
bob, bob_pf = mk_user(db, "bob", cash=100_000.0)
bob.display_name = "Bobby"
bob.bio = "long-term holder"
db.commit()
fake.spot["AAPL"] = 200.0
execute_trade(db, bob_pf, "AAPL", "buy", 100)     # 20,000 of 100,000
execute_trade(db, bob_pf, "MSFT", "buy", 25)      # 10,000 of 100,000
fake.spot["AAPL"] = 220.0                          # +10% on AAPL

view = build_public_profile(db, bob, alice)
data = view.model_dump()

check("display_name surfaced", data["display_name"] == "Bobby")
check("bio surfaced", data["bio"] == "long-term holder")
check("no email field", "email" not in data)
check("no cash/balance field", not any("cash" in k or "balance" in k for k in data))
check("no total_value field", "total_value" not in data)
check("portfolio name surfaced", data["portfolio_name"] == "Default")

# total return: cash 70,000 + AAPL 22,000 + MSFT 10,000 = 102,000 → +2%
check("total_return_percent correct", abs(data["total_return_percent"] - 2.0) < 1e-6,
      f"got {data['total_return_percent']}")

check("two holdings listed", len(data["holdings"]) == 2, f"got {len(data['holdings'])}")
allowed = {"symbol", "weight_percent", "unrealized_pl_percent"}
check("holding rows expose only symbol/weight/return",
      all(set(h) == allowed for h in data["holdings"]),
      f"got {set(data['holdings'][0])}")
by_symbol = {h["symbol"]: h for h in data["holdings"]}
# gross = 22,000 + 10,000 = 32,000 → AAPL 68.75%, MSFT 31.25%
check("weight_percent is a share of gross value",
      abs(by_symbol["AAPL"]["weight_percent"] - 68.75) < 1e-6,
      f"got {by_symbol['AAPL']['weight_percent']}")
check("weights sum to 100", abs(sum(h["weight_percent"] for h in data["holdings"]) - 100.0) < 1e-6)
check("unrealized_pl_percent surfaced", abs(by_symbol["AAPL"]["unrealized_pl_percent"] - 10.0) < 1e-6,
      f"got {by_symbol['AAPL']['unrealized_pl_percent']}")
check("holdings sorted by weight desc", data["holdings"][0]["symbol"] == "AAPL")
db.close()

# ===========================================================================
print("\n[4] Which portfolio is public")
db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
bob, bob_pf = mk_user(db, "bob", publish=False)
check("unpublished user has no public portfolio", public_portfolio_of(db, bob) is None)
check("profile of unpublished user has no holdings",
      build_public_profile(db, bob, alice).holdings == [])
check("profile of unpublished user has no return",
      build_public_profile(db, bob, alice).total_return_percent is None)

bob.public_portfolio_id = alice_pf.id  # someone else's portfolio
db.commit()
check("an id pointing at another user's portfolio resolves to None",
      public_portfolio_of(db, bob) is None)

bob.public_portfolio_id = 9999  # dangling
db.commit()
check("a dangling id resolves to None", public_portfolio_of(db, bob) is None)

bob.public_portfolio_id = bob_pf.id
db.commit()
check("own portfolio resolves", public_portfolio_of(db, bob).id == bob_pf.id)
db.close()

# ===========================================================================
print("\n[5] PATCH /users/me")
db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
bob, bob_pf = mk_user(db, "bob")
second = Portfolio(user_id=alice.id, name="Swing", cash_balance=1000.0, starting_balance=1000.0)
db.add(second)
db.commit()

update_me(ProfileUpdate(display_name="  Alice A  ", bio="  hello  "), db, alice)
check("display_name trimmed", alice.display_name == "Alice A", f"got {alice.display_name!r}")
check("bio trimmed", alice.bio == "hello", f"got {alice.bio!r}")

update_me(ProfileUpdate(bio="updated"), db, alice)
check("omitted fields are untouched", alice.display_name == "Alice A" and alice.bio == "updated")

update_me(ProfileUpdate(display_name=None), db, alice)
check("explicit null clears the field", alice.display_name is None)

update_me(ProfileUpdate(display_name="   "), db, alice)
check("whitespace-only clears the field", alice.display_name is None)

update_me(ProfileUpdate(public_portfolio_id=second.id), db, alice)
check("public portfolio switched", alice.public_portfolio_id == second.id)
update_me(ProfileUpdate(public_portfolio_id=None), db, alice)
check("public portfolio cleared (private)", alice.public_portfolio_id is None)

expect_http("can't publish someone else's portfolio",
            lambda: update_me(ProfileUpdate(public_portfolio_id=bob_pf.id), db, alice), status=404)
expect_http("can't publish a portfolio that doesn't exist",
            lambda: update_me(ProfileUpdate(public_portfolio_id=424242), db, alice), status=404)

comp = mk_competition(db, alice, starts_in=-1, ends_in=60)
join_competition(comp.id, db, alice)
entry = entry_of(db, comp, alice)
expect_http("can't publish a competition entry",
            lambda: update_me(ProfileUpdate(public_portfolio_id=entry.id), db, alice), status=400)
db.close()

# ===========================================================================
print("\n[6] Activity feed")
db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
bob, bob_pf = mk_user(db, "bob")
carol, carol_pf = mk_user(db, "carol")
bob.display_name = "Bobby"
db.commit()

# A second, unpublished portfolio for bob — its trades must stay private.
bob_private = Portfolio(user_id=bob.id, name="Private", cash_balance=50_000.0,
                        starting_balance=50_000.0)
db.add(bob_private)
db.commit()

check("feed is empty when following nobody", build_feed(db, alice) == [])

now = datetime.now(timezone.utc)
db.add_all([
    Trade(portfolio_id=bob_pf.id, symbol="AAPL", side="buy", quantity=13, price=200.0,
          executed_at=now - timedelta(minutes=5)),
    Trade(portfolio_id=bob_pf.id, symbol="MSFT", side="sell", quantity=4, price=400.0,
          executed_at=now - timedelta(minutes=1)),
    Trade(portfolio_id=bob_private.id, symbol="TSLA", side="buy", quantity=1, price=300.0,
          executed_at=now),
    Trade(portfolio_id=carol_pf.id, symbol="NVDA", side="buy", quantity=2, price=100.0,
          executed_at=now),
    OptionTrade(portfolio_id=bob_pf.id, underlying="AAPL", occ_symbol="AAPL_C210",
                option_type="call", strike=210.0, expiration=date(2026, 9, 18), action="buy",
                quantity=2, price=5.0, executed_at=now - timedelta(minutes=3)),
    OptionTrade(portfolio_id=bob_pf.id, underlying="AAPL", occ_symbol="AAPL_C250",
                option_type="call", strike=250.0, expiration=date(2026, 9, 18), action="settle",
                quantity=1, price=0.0, executed_at=now - timedelta(minutes=2)),
])
db.commit()

follow("bob", db, alice)
items = build_feed(db, alice)
labels = [i.label for i in items]

check("feed shows the followee's public-portfolio trades", "AAPL" in labels and "MSFT" in labels)
check("feed excludes their unpublished portfolio", "TSLA" not in labels)
check("feed excludes people you don't follow", "NVDA" not in labels)
check("feed excludes option settlements",
      all("250" not in lab for lab in labels), f"labels={labels}")
check("feed includes option fills", any(i.kind == "option" for i in items))
check("option row is labelled readably",
      any(i.label == "AAPL $210 call 2026-09-18" for i in items), f"labels={labels}")
check("feed has 3 items (2 stock + 1 option)", len(items) == 3, f"got {len(items)}")
check("newest first", [i.label for i in items][0] == "MSFT", f"got {labels}")
check("carries the followee's identity",
      all(i.username == "bob" and i.display_name == "Bobby" for i in items))
check("carries the fill price", any(abs(i.price - 200.0) < 1e-9 for i in items))
check("timestamps are timezone-aware UTC",
      all(i.executed_at.tzinfo is not None for i in items))

row = items[0].model_dump()
check("feed rows carry no quantity", "quantity" not in row)
check("feed rows carry no dollar total",
      not any(k in row for k in ("total", "notional", "value", "cash")), f"keys={set(row)}")
check("stable ids distinguish stock from option trades",
      len({i.id for i in items}) == 3 and any(i.id.startswith("o") for i in items))
check("limit is respected", len(build_feed(db, alice, limit=1)) == 1)

unfollow("bob", db, alice)
check("feed empties after unfollowing", build_feed(db, alice) == [])
db.close()

# ===========================================================================
print("\n[7] Competition status is derived from the clock")
db = fresh_db()
alice, _ = mk_user(db, "alice")
check("before starts_at → upcoming",
      competition_status(mk_competition(db, alice, 10, 60)) == UPCOMING)
check("inside the window → active",
      competition_status(mk_competition(db, alice, -10, 60)) == ACTIVE)
check("after ends_at → ended",
      competition_status(mk_competition(db, alice, -60, -10)) == ENDED)
db.close()

# ===========================================================================
print("\n[8] Trades are gated to the competition window")
fake.market_state = "REGULAR"
fake.spot["AAPL"] = 200.0

db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
upcoming = mk_competition(db, alice, starts_in=10, ends_in=60, name="Later")
join_competition(upcoming.id, db, alice)
early_entry = entry_of(db, upcoming, alice)
expect_trading_error("trade before the start is rejected",
                     lambda: execute_trade(db, early_entry, "AAPL", "buy", 1),
                     contains="hasn't started")

live = mk_competition(db, alice, starts_in=-1, ends_in=60, name="Live")
join_competition(live.id, db, alice)
entry = entry_of(db, live, alice)
t = execute_trade(db, entry, "AAPL", "buy", 10)
check("trade inside the window fills", t.price == 200.0 and t.symbol == "AAPL")
check("entry cash debited", abs(entry.cash_balance - 48_000.0) < 1e-6, f"cash={entry.cash_balance}")

check("an ordinary portfolio is unaffected by the gate",
      execute_trade(db, alice_pf, "AAPL", "buy", 1).symbol == "AAPL")

live.ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
db.commit()
expect_trading_error("trade after the end is rejected",
                     lambda: execute_trade(db, entry, "AAPL", "buy", 1),
                     contains="has ended")
expect_trading_error("selling after the end is rejected too (entry is read-only)",
                     lambda: execute_trade(db, entry, "AAPL", "sell", 1),
                     contains="has ended")
db.close()

# ===========================================================================
print("\n[9] Option orders share the same gate")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C210", "call", 210.0, 5.0)
db = fresh_db()
alice, _ = mk_user(db, "alice")
comp = mk_competition(db, alice, starts_in=-1, ends_in=60)
join_competition(comp.id, db, alice)
entry = entry_of(db, comp, alice)

req = OptionOrderRequest(occ_symbol="AAPL_C210", underlying="AAPL", expiration=FUTURE_EXP,
                         option_type="call", strike=210.0, side="buy", quantity=1)
ot = place_option_order(db, entry, req)
check("option order fills inside the window", ot.action == "buy" and ot.price == 5.0)

comp.ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
db.commit()
expect_trading_error("option order after the end is rejected",
                     lambda: place_option_order(db, entry, req), contains="has ended")
db.close()

# ===========================================================================
print("\n[10] Finalization freezes results and cancels resting orders")
fake.marks.clear(); fake.meta.clear()
fake.spot["AAPL"] = 200.0
db = fresh_db()
alice, _ = mk_user(db, "alice")
comp = mk_competition(db, alice, starts_in=-10, ends_in=60)
join_competition(comp.id, db, alice)
entry = entry_of(db, comp, alice)
execute_trade(db, entry, "AAPL", "buy", 100)   # 20,000 of 50,000
resting = Order(portfolio_id=entry.id, symbol="AAPL", side="buy", order_type="limit",
                quantity=1, limit_price=1.0, status="open")
db.add(resting)
db.commit()

finalize_ended_competitions(db)
check("an active competition isn't finalized", entry.final_value is None)

fake.spot["AAPL"] = 240.0                      # 30,000 cash + 24,000 = 54,000 → +8%
comp.ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
db.commit()
finalize_ended_competitions(db)
check("final_value snapshotted at the bell", abs((entry.final_value or 0) - 54_000.0) < 1e-6,
      f"got {entry.final_value}")
db.refresh(resting)
check("open resting orders are cancelled", resting.status == "cancelled", f"got {resting.status}")
check("cancellation is explained", resting.note == "Competition ended")

rows = standings_route(comp.id, db, alice)
check("standings read the snapshot", abs(rows[0].return_percent - 8.0) < 1e-6,
      f"got {rows[0].return_percent}")
check("row is marked final", rows[0].final is True)

fake.spot["AAPL"] = 100.0                      # a crash after the bell must not move results
rows = standings_route(comp.id, db, alice)
check("results stay frozen as prices move", abs(rows[0].return_percent - 8.0) < 1e-6,
      f"got {rows[0].return_percent}")

finalize_ended_competitions(db)
check("finalization is idempotent", abs((entry.final_value or 0) - 54_000.0) < 1e-6,
      f"got {entry.final_value}")
db.close()

# ===========================================================================
print("\n[11] Standings ranking")
fake.spot["AAPL"] = 200.0
db = fresh_db()
alice, _ = mk_user(db, "alice")
bob, _ = mk_user(db, "bob")
carol, _ = mk_user(db, "carol")
comp = mk_competition(db, alice, starts_in=-10, ends_in=60)
for u in (alice, bob, carol):
    join_competition(comp.id, db, u)

winner = entry_of(db, comp, bob)
execute_trade(db, winner, "AAPL", "buy", 100)
fake.spot["AAPL"] = 240.0                      # bob: +8%; alice & carol: all cash, 0%

rows = standings_route(comp.id, db, carol)
check("three entrants ranked", len(rows) == 3, f"got {len(rows)}")
check("best return first", rows[0].username == "bob" and abs(rows[0].return_percent - 8.0) < 1e-6,
      f"got {rows[0].username} {rows[0].return_percent}")
check("rank 1 for the leader", rows[0].rank == 1)
check("ties share a rank", rows[1].rank == 2 and rows[2].rank == 2,
      f"got {rows[1].rank}, {rows[2].rank}")
check("flat entries show 0%", abs(rows[1].return_percent) < 1e-9)
check("is_me marks the requesting user",
      [r.username for r in rows if r.is_me] == ["carol"])
check("standings expose no dollar values",
      not any(k in rows[0].model_dump() for k in ("total_value", "cash_balance", "final_value")))
check("rows aren't final while the contest runs", all(r.final is False for r in rows))

prof = build_public_profile(db, bob, alice)
check("profile lists the competition record", len(prof.competitions) == 1)
check("record carries rank and entrants",
      prof.competitions[0].rank == 1 and prof.competitions[0].entrants == 3,
      f"got rank={prof.competitions[0].rank} entrants={prof.competitions[0].entrants}")
check("record carries status", prof.competitions[0].status == ACTIVE)
db.close()

# ===========================================================================
print("\n[12] Join / leave / delete rules")
db = fresh_db()
alice, _ = mk_user(db, "alice")
bob, _ = mk_user(db, "bob")

created = create_competition(
    CompetitionCreate(
        name="  Summer Cup  ", description="  fun  ", starting_cash=25_000.0,
        starts_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
    ),
    db, alice,
)
check("created competition is active", created.status == ACTIVE)
check("name trimmed", created.name == "Summer Cup")
check("creator recorded", created.creator_username == "alice" and created.is_creator is True)
check("creating doesn't auto-join", created.joined is False and created.entrants == 0)

expect_http("a competition that's already over is rejected",
            lambda: create_competition(
                CompetitionCreate(
                    name="Stale",
                    starts_at=datetime.now(timezone.utc) - timedelta(hours=2),
                    ends_at=datetime.now(timezone.utc) - timedelta(hours=1),
                ), db, alice),
            status=400)

joined = join_competition(created.id, db, bob)
check("joining reports the entry", joined.joined is True and joined.entry_portfolio_id is not None)
check("entrant counted", joined.entrants == 1)
entry = entry_of(db, db.get(Competition, created.id), bob)
check("entry funded with the contest's starting cash",
      entry.cash_balance == 25_000.0 and entry.starting_balance == 25_000.0)
check("entry named after the competition", entry.name == "Summer Cup")

expect_http("joining twice is a conflict",
            lambda: join_competition(created.id, db, bob), status=409)
expect_http("joining an unknown competition 404s",
            lambda: join_competition(99999, db, bob), status=404)

expect_http("leaving one you never joined 404s",
            lambda: leave_competition(created.id, db, alice), status=404)
expect_http("a non-creator can't delete",
            lambda: delete_competition(created.id, db, bob), status=403)

listed = list_competitions(db, bob)
check("listing shows the entrant's own join state",
      len(listed) == 1 and listed[0].joined is True)
check("listing shows non-creator status", listed[0].is_creator is False)

leave_competition(created.id, db, bob)
check("leaving deletes the entry portfolio",
      db.query(Portfolio).filter(Portfolio.competition_id == created.id).count() == 0)

# Ended competitions are read-only and permanent.
ended = mk_competition(db, alice, starts_in=-120, ends_in=-60, name="Old Cup")
expect_http("can't join an ended competition",
            lambda: join_competition(ended.id, db, bob), status=400)
expect_http("can't delete an ended competition",
            lambda: delete_competition(ended.id, db, alice), status=400)

live2 = mk_competition(db, alice, starts_in=-1, ends_in=60, name="Live Cup")
join_competition(live2.id, db, bob)
bob_entry = entry_of(db, live2, bob)
live2.ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
db.commit()
expect_http("can't leave once results are final",
            lambda: leave_competition(live2.id, db, bob), status=400)
check("the entry survives the failed leave", db.get(Portfolio, bob_entry.id) is not None)

# Creator deleting a live competition takes its entries with it.
live3 = mk_competition(db, alice, starts_in=-1, ends_in=60, name="Doomed")
join_competition(live3.id, db, bob)
doomed_entry_id = entry_of(db, live3, bob).id
delete_competition(live3.id, db, alice)
check("deleting a competition removes it", db.get(Competition, live3.id) is None)
check("its entries are cascaded away", db.get(Portfolio, doomed_entry_id) is None)
db.close()

# ===========================================================================
print("\n[13] Portfolio list & delete guards")
db = fresh_db()
alice, alice_pf = mk_user(db, "alice")
swing = Portfolio(user_id=alice.id, name="Swing", cash_balance=5_000.0, starting_balance=5_000.0)
db.add(swing)
db.commit()
check("two ordinary portfolios coexist (NULL competition_id isn't unique-constrained)",
      db.query(Portfolio).filter(Portfolio.user_id == alice.id).count() == 2)

comp = mk_competition(db, alice, starts_in=-1, ends_in=60, name="Cup")
join_competition(comp.id, db, alice)
entry = entry_of(db, comp, alice)

rows = list_portfolios(db, alice)
check("all three portfolios listed", len(rows) == 3, f"got {len(rows)}")
check("own portfolios come first", [r.name for r in rows[:2]] == ["Default", "Swing"],
      f"got {[r.name for r in rows]}")
check("the entry is tagged with its competition",
      rows[2].competition_id == comp.id and rows[2].competition_name == "Cup")
check("the entry carries the competition's status", rows[2].competition_status == ACTIVE)
check("ordinary portfolios have no competition tag",
      rows[0].competition_id is None and rows[0].competition_status is None)

expect_http("a competition entry can't be deleted directly",
            lambda: delete_portfolio(entry.id, db, alice), status=400)
expect_http("a competition entry can't be reset (no erasing a bad run)",
            lambda: reset_portfolio(entry, db), status=400)
check("an ordinary portfolio can still be reset",
      reset_portfolio(swing, db).cash_balance == 5_000.0)
expect_http("another user's portfolio can't be deleted",
            lambda: delete_portfolio(alice_pf.id, db, mk_user(db, "mallory")[0]), status=404)

check("public portfolio starts as the default one", alice.public_portfolio_id == alice_pf.id)
delete_portfolio(alice_pf.id, db, alice)
check("deleting the published portfolio clears the pointer", alice.public_portfolio_id is None)

# Only ordinary portfolios count toward "keep at least one" — the entry doesn't prop it up.
expect_http("can't delete the last ordinary portfolio",
            lambda: delete_portfolio(swing.id, db, alice), status=400)
check("the entry is still there", db.get(Portfolio, entry.id) is not None)
db.close()

# ===========================================================================
print("\n[14] One entry per user per competition (DB constraint)")
db = fresh_db()
alice, _ = mk_user(db, "alice")
comp = mk_competition(db, alice, starts_in=-1, ends_in=60)
join_competition(comp.id, db, alice)
db.add(Portfolio(user_id=alice.id, name="Sneaky", cash_balance=1.0, starting_balance=1.0,
                 competition_id=comp.id))
try:
    db.commit()
    check("duplicate entry blocked by the unique constraint", False, "commit succeeded")
except IntegrityError:
    db.rollback()
    check("duplicate entry blocked by the unique constraint", True)
db.close()

# ===========================================================================
print(f"\n==== {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
