"""Offline verification for the options trading feature.

Runs the whole options service against an in-memory SQLite DB and a fake, always-REGULAR market
data provider (the live market is usually closed during dev). Exercises fills, collateral rules,
market-hours + 0DTE gates, expiry settlement, and portfolio valuation.

Run:  ./.venv/Scripts/python.exe scripts/test_options_offline.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.market_data as market_data
import app.services.options as options
from app.db.base import Base
from app.models.holding import Holding
from app.models.option_order import OptionOrder
from app.models.option_position import OptionPosition
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.market import OptionContract
from app.schemas.market import Quote
from app.schemas.portfolio import OptionOrderRequest
from app.services.options import (
    place_option_order,
    process_open_option_orders,
    settle_expired_options,
)
from app.services.orders import monitor_bankruptcies
from app.services.trading import TradingError, value_portfolio

ET = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------
class FakeProvider:
    def __init__(self) -> None:
        self.market_state = "REGULAR"
        self.spot: dict[str, float] = {"AAPL": 200.0, "SPX": 5000.0}
        # occ_symbol -> mark (per share)
        self.marks: dict[str, float] = {}
        # occ_symbol -> (option_type, strike)
        self.meta: dict[str, tuple[str, float]] = {}

    def add_contract(self, occ: str, option_type: str, strike: float, mark: float) -> None:
        self.marks[occ] = mark
        self.meta[occ] = (option_type, strike)

    def get_quote(self, symbol: str) -> Quote:
        p = self.spot.get(symbol.upper(), 100.0)
        return Quote(symbol=symbol.upper(), price=p, effective_price=p, market_state=self.market_state)

    def get_option_contract(self, underlying, expiration, option_type, strike):
        for occ, (otype, k) in self.meta.items():
            if otype == option_type and abs(k - strike) < 1e-6:
                return OptionContract(
                    occ_symbol=occ,
                    option_type=otype,
                    strike=k,
                    mark=self.marks[occ],
                    bid=self.marks[occ],
                    ask=self.marks[occ],
                    last_price=self.marks[occ],
                )
        return None

    def get_option_expirations(self, symbol):
        return []

    def get_option_chain(self, symbol, expiration=None):
        raise NotImplementedError


fake = FakeProvider()
market_data._provider = fake  # patch singleton


def fresh_db(cash: float = 100_000.0):
    # A brand-new in-memory engine per test → full isolation (no cross-test leakage).
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, future=True)()
    user = User(email="t@t.com", username="t", hashed_password="x")
    db.add(user)
    db.flush()
    pf = Portfolio(user_id=user.id, name="Test", cash_balance=cash, starting_balance=cash)
    db.add(pf)
    db.commit()
    return db, pf


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


def expect_error(name: str, fn) -> None:
    global passed, failed
    try:
        fn()
        failed += 1
        print(f"  FAIL  {name}  (expected TradingError, none raised)")
    except TradingError as exc:
        passed += 1
        print(f"  PASS  {name}  -> rejected: {exc}")


NEXT_FRI = (date.today() + timedelta(days=30)).isoformat()


def req(**kw):
    base = dict(
        occ_symbol=kw["occ"],
        underlying=kw.get("underlying", "AAPL"),
        expiration=kw.get("expiration", NEXT_FRI),
        option_type=kw["option_type"],
        strike=kw["strike"],
        side=kw["side"],
        quantity=kw["quantity"],
    )
    return OptionOrderRequest(**base)


# ===========================================================================
print("\n[1] Buy-to-open long call → cash debited, position + trade created")
fake.market_state = "REGULAR"
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C210", "call", 210.0, 5.0)
db, pf = fresh_db()
t = place_option_order(db, pf, req(occ="AAPL_C210", option_type="call", strike=210.0, side="buy", quantity=2))
check("cash debited by 5*100*2=1000", abs(pf.cash_balance - 99_000.0) < 1e-6, f"cash={pf.cash_balance}")
pos = db.query(OptionPosition).one()
check("position qty +2", pos.quantity == 2.0)
check("avg_price 5.0", pos.avg_price == 5.0)
check("collateral None (long)", pos.collateral_kind is None)
check("trade action buy", t.action == "buy" and t.realized_pl is None)

print("\n[2] Sell-to-close long call at higher mark → realized P&L booked, cash credited")
fake.marks["AAPL_C210"] = 8.0
t2 = place_option_order(db, pf, req(occ="AAPL_C210", option_type="call", strike=210.0, side="sell", quantity=2))
check("realized = (8-5)*100*2 = 600", abs((t2.realized_pl or 0) - 600.0) < 1e-6, f"realized={t2.realized_pl}")
check("cash back to 99000+1600=100600", abs(pf.cash_balance - 100_600.0) < 1e-6, f"cash={pf.cash_balance}")
check("position closed (deleted)", db.query(OptionPosition).count() == 0)
db.close()

print("\n[3] Cash-secured put: reserve strike*100, block over-reserving")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_P190", "put", 190.0, 4.0)
db, pf = fresh_db(cash=20_000.0)
place_option_order(db, pf, req(occ="AAPL_P190", option_type="put", strike=190.0, side="sell", quantity=1))
pos = db.query(OptionPosition).one()
check("CSP collateral_kind", pos.collateral_kind == "cash_secured" and pos.quantity == -1.0)
check("premium credited 4*100=400", abs(pf.cash_balance - 20_400.0) < 1e-6, f"cash={pf.cash_balance}")
out = value_portfolio(db, pf)
check("reserved_cash = 190*100 = 19000", abs(out.reserved_cash - 19_000.0) < 1e-6, f"reserved={out.reserved_cash}")
# Second CSP needs another 19000 reserved but only ~1400 free → blocked.
expect_error(
    "over-reserving second CSP blocked",
    lambda: place_option_order(db, pf, req(occ="AAPL_P190", option_type="put", strike=190.0, side="sell", quantity=1)),
)
db.close()

print("\n[4] Covered call: blocked without shares, allowed with 100 shares/contract")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C220", "call", 220.0, 3.0)
db, pf = fresh_db()
expect_error(
    "naked call rejected",
    lambda: place_option_order(db, pf, req(occ="AAPL_C220", option_type="call", strike=220.0, side="sell", quantity=1)),
)
db.add(Holding(portfolio_id=pf.id, symbol="AAPL", quantity=100, avg_cost=150.0))
db.commit()
tc = place_option_order(db, pf, req(occ="AAPL_C220", option_type="call", strike=220.0, side="sell", quantity=1))
pos = db.query(OptionPosition).filter(OptionPosition.occ_symbol == "AAPL_C220").one()
check("covered call written", pos.quantity == -1.0 and pos.collateral_kind == "covered")
check("premium credited 3*100=300", abs(pf.cash_balance - 100_300.0) < 1e-6, f"cash={pf.cash_balance}")
# A 2nd covered call needs 200 shares but only 100 owned → blocked.
expect_error(
    "2nd covered call blocked (only 100 sh)",
    lambda: place_option_order(db, pf, req(occ="AAPL_C220", option_type="call", strike=220.0, side="sell", quantity=1)),
)
db.close()

print("\n[5] Market-hours + 0DTE gates")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C205", "call", 205.0, 2.0)
fake.add_contract("SPX_C5010", "call", 5010.0, 2.0)
today_iso = date.today().isoformat()

# non-REGULAR rejected
fake.market_state = "CLOSED"
db, pf = fresh_db()
expect_error(
    "CLOSED session rejected",
    lambda: place_option_order(db, pf, req(occ="AAPL_C205", option_type="call", strike=205.0, side="buy", quantity=1)),
)
db.close()

# 0DTE non-index within final 15 min rejected; SPX allowed. Patch _now_et to 3:50 PM ET today.
fake.market_state = "REGULAR"
real_now = options._now_et
fixed = datetime.now(ET).replace(hour=15, minute=50, second=0, microsecond=0)
options._now_et = lambda: fixed

db, pf = fresh_db()
expect_error(
    "0DTE AAPL rejected at 3:50pm",
    lambda: place_option_order(db, pf, req(occ="AAPL_C205", underlying="AAPL", expiration=today_iso, option_type="call", strike=205.0, side="buy", quantity=1)),
)
t_spx = place_option_order(db, pf, req(occ="SPX_C5010", underlying="SPX", expiration=today_iso, option_type="call", strike=5010.0, side="buy", quantity=1))
check("0DTE SPX allowed at 3:50pm", t_spx.action == "buy")
db.close()

# Same 0DTE AAPL allowed earlier (11:00 AM)
fixed2 = datetime.now(ET).replace(hour=11, minute=0, second=0, microsecond=0)
options._now_et = lambda: fixed2
db, pf = fresh_db()
t_early = place_option_order(db, pf, req(occ="AAPL_C205", underlying="AAPL", expiration=today_iso, option_type="call", strike=205.0, side="buy", quantity=1))
check("0DTE AAPL allowed at 11:00am", t_early.action == "buy")
db.close()
options._now_et = real_now

print("\n[6] Expiry settlement: long ITM receives intrinsic; OTM worthless")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C190", "call", 190.0, 12.0)   # ITM: spot 200 > 190
fake.add_contract("AAPL_C250", "call", 250.0, 0.5)    # OTM: spot 200 < 250
fake.spot["AAPL"] = 200.0
db, pf = fresh_db()
# Buy both (long)
place_option_order(db, pf, req(occ="AAPL_C190", option_type="call", strike=190.0, side="buy", quantity=1))
place_option_order(db, pf, req(occ="AAPL_C250", option_type="call", strike=250.0, side="buy", quantity=1))
cash_before = pf.cash_balance
# Backdate expiration to yesterday so they settle now.
yesterday = date.today() - timedelta(days=1)
for p in db.query(OptionPosition).all():
    p.expiration = yesterday
db.commit()
settle_expired_options(db)
check("all expired positions removed", db.query(OptionPosition).count() == 0)
# ITM 190 call pays intrinsic (200-190)*100 = 1000; OTM 250 pays 0.
check("cash += 1000 intrinsic", abs(pf.cash_balance - (cash_before + 1000.0)) < 1e-6, f"cash={pf.cash_balance}, before={cash_before}")
settle_trades = [x for x in pf.option_trades if x.action == "settle"]
check("two settle trades written", len(settle_trades) == 2)
db.close()

print("\n[7] Valuation: option MV in total, gross; reserved off buying power")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C210", "call", 210.0, 5.0)
db, pf = fresh_db(cash=50_000.0)
place_option_order(db, pf, req(occ="AAPL_C210", option_type="call", strike=210.0, side="buy", quantity=1))
# cash now 49500; mark still 5 → option MV = 500
out = value_portfolio(db, pf)
check("total_value = cash + option MV = 49500+500 = 50000", abs(out.total_value - 50_000.0) < 1e-6, f"total={out.total_value}")
check("one option position in view", len(out.option_positions) == 1)
check("option market_value 500", abs((out.option_positions[0].market_value or 0) - 500.0) < 1e-6)
# ratio=1.0 → buying_power = total - gross - reserved = 50000 - 500 - 0 = 49500
check("buying_power = 49500", abs(out.buying_power - 49_500.0) < 1e-6, f"bp={out.buying_power}")
db.close()

print("\n[8] Resting option orders: limit buy fills only when mark ≤ limit and session is REGULAR")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C210", "call", 210.0, 5.0)
fake.market_state = "REGULAR"
db, pf = fresh_db()


def _add_order(**kw) -> OptionOrder:
    o = OptionOrder(
        portfolio_id=pf.id,
        underlying=kw.get("underlying", "AAPL"),
        occ_symbol=kw["occ"],
        option_type=kw["option_type"],
        strike=kw["strike"],
        expiration=date.fromisoformat(kw.get("expiration", NEXT_FRI)),
        side=kw["side"],
        order_type=kw["order_type"],
        quantity=kw["quantity"],
        limit_price=kw.get("limit_price"),
        stop_price=kw.get("stop_price"),
        trail_percent=kw.get("trail_percent"),
        status="open",
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


# Limit buy at 4.0 with mark 5.0 → not triggered, stays open.
o1 = _add_order(occ="AAPL_C210", option_type="call", strike=210.0, side="buy",
                order_type="limit", quantity=1, limit_price=4.0)
process_open_option_orders(db)
db.refresh(o1)
check("limit buy stays open while mark(5) > limit(4)", o1.status == "open", f"status={o1.status}")

# Mark drops to 3.5 → triggers, fills at mark, position + trade created.
fake.marks["AAPL_C210"] = 3.5
process_open_option_orders(db)
db.refresh(o1)
check("limit buy fills when mark(3.5) ≤ limit(4)", o1.status == "filled", f"status={o1.status}")
check("fill_price = mark 3.5", abs((o1.fill_price or 0) - 3.5) < 1e-6, f"fill={o1.fill_price}")
check("filled_option_trade_id set", o1.filled_option_trade_id is not None)
check("position opened qty +1", db.query(OptionPosition).filter(OptionPosition.occ_symbol == "AAPL_C210").one().quantity == 1.0)
db.close()

print("\n[9] Resting order stays open when the session is not REGULAR")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C210", "call", 210.0, 3.0)
fake.market_state = "CLOSED"
db, pf = fresh_db()
o2 = _add_order(occ="AAPL_C210", option_type="call", strike=210.0, side="buy",
                order_type="limit", quantity=1, limit_price=4.0)  # would trigger if REGULAR
process_open_option_orders(db)
db.refresh(o2)
check("closed session leaves order open", o2.status == "open", f"status={o2.status}")
db.close()

print("\n[10] Triggered but uncollateralizable write → rejected (no shares for a covered call)")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C220", "call", 220.0, 5.0)
fake.market_state = "REGULAR"
db, pf = fresh_db()
# Sell limit call at 3.0: mark 5.0 ≥ 3.0 → triggers, but naked (no shares) → place rejects.
o3 = _add_order(occ="AAPL_C220", option_type="call", strike=220.0, side="sell",
                order_type="limit", quantity=1, limit_price=3.0)
process_open_option_orders(db)
db.refresh(o3)
check("naked covered-call write rejected", o3.status == "rejected", f"status={o3.status}")
check("rejection note recorded", bool(o3.note))
check("no position created", db.query(OptionPosition).count() == 0)
db.close()

print("\n[11] monitor_bankruptcies cancels open option orders when a portfolio is wiped out")
fake.marks.clear(); fake.meta.clear()
fake.add_contract("AAPL_C210", "call", 210.0, 5.0)
fake.spot["AAPL"] = 200.0
fake.market_state = "REGULAR"
db, pf = fresh_db(cash=0.0)
# A short stock position priced at spot drives total value negative → triggers the lock.
db.add(Holding(portfolio_id=pf.id, symbol="AAPL", quantity=-100, avg_cost=200.0))
db.commit()
o4 = _add_order(occ="AAPL_C210", option_type="call", strike=210.0, side="buy",
                order_type="limit", quantity=1, limit_price=1.0)  # won't trigger; just needs to exist
monitor_bankruptcies(db)
db.refresh(pf)
db.refresh(o4)
check("portfolio locked when wiped out", pf.locked is True)
check("open option order cancelled on lock", o4.status == "cancelled", f"status={o4.status}")
check("cancel note recorded", o4.note == "Portfolio wiped out")
db.close()

# ===========================================================================
print(f"\n==== {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
