"""Deterministically replay raw Kalshi order-book JSONL.

Sequence numbers belong to a WebSocket subscription, not to an individual
market.  ``ReplayState`` therefore checks continuity once per connection/SID
and maintains independent books by ticker.  Any gap quarantines every book on
that subscription until each market receives a fresh exchange snapshot.
"""
from __future__ import annotations
import argparse, hashlib, json
from dataclasses import dataclass, field
from pathlib import Path


class OrderBookQuarantined(RuntimeError):
    """Raised when a fill is requested from a book with an unresolved gap."""

@dataclass
class Book:
    yes: dict[int, float] = field(default_factory=dict)
    no: dict[int, float] = field(default_factory=dict)
    last_seq: int | None = None
    gaps: int = 0
    quarantined: bool = False

    def to_dict(self) -> dict:
        return {
            "yes": [[price, self.yes[price]] for price in sorted(self.yes)],
            "no": [[price, self.no[price]] for price in sorted(self.no)],
            "last_seq": self.last_seq,
            "gaps": self.gaps,
            "quarantined": self.quarantined,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "Book":
        return cls(
            yes={int(price): float(quantity) for price, quantity in value.get("yes", [])},
            no={int(price): float(quantity) for price, quantity in value.get("no", [])},
            last_seq=value.get("last_seq"),
            gaps=int(value.get("gaps", 0)),
            quarantined=bool(value.get("quarantined", False)),
        )

    @staticmethod
    def _cents(value: object) -> int:
        """Normalize legacy integer cents or current dollar strings."""
        text = str(value)
        if "." in text:
            return int(round(float(text) * 100))
        number = float(text)
        # Current *_dollars_fp fields are decimal dollars; legacy fields are
        # integer cents. The caller selects the appropriate representation.
        return int(round(number))

    @staticmethod
    def _snapshot_levels(body: dict, side: str) -> list[tuple[int, float]]:
        legacy = body.get(side)
        if legacy is not None:
            return [(int(price), float(quantity)) for price, quantity in legacy]
        dollar_key = f"{side}_dollars_fp"
        return [(int(round(float(price) * 100)), float(quantity))
                for price, quantity in (body.get(dollar_key) or [])]

    def apply(self, message: dict, *, track_sequence: bool = True) -> None:
        body = message.get("msg", message)
        typ = message.get("type", body.get("type", ""))
        seq = message.get("seq", body.get("seq", message.get("sequence")))
        is_snapshot = typ == "orderbook_snapshot" or ("yes" in body and "no" in body) or "yes_dollars_fp" in body
        if self.quarantined and not is_snapshot:
            return
        if track_sequence and isinstance(seq, int):
            if self.last_seq is not None and seq > self.last_seq + 1:
                self.gaps += 1
                self.quarantined = True
                if not is_snapshot:
                    return
            if self.last_seq is not None and seq <= self.last_seq: return
            self.last_seq = seq
        if is_snapshot:
            self.yes = {p: q for p, q in self._snapshot_levels(body, "yes") if q > 0}
            self.no = {p: q for p, q in self._snapshot_levels(body, "no") if q > 0}
            self.quarantined = False
        elif typ == "orderbook_delta" or {"side", "price", "delta"} <= body.keys() or {"side", "price_dollars", "delta_fp"} <= body.keys():
            side_name = str(body.get("side", "")).lower()
            if side_name not in {"yes", "no"}:
                raise ValueError(f"unknown order-book side: {body.get('side')!r}")
            side = self.yes if side_name == "yes" else self.no
            if "price" in body:
                price = int(body["price"]); delta = float(body["delta"])
            else:
                price = int(round(float(body["price_dollars"]) * 100)); delta = float(body["delta_fp"])
            side[price] = side.get(price, 0.0) + delta
            if side[price] <= 0: side.pop(price, None)


@dataclass
class ReplayState:
    """Reconstruct multiple market books with subscription-level sequencing."""

    books: dict[str, Book] = field(default_factory=dict)
    last_sequence: dict[str, int] = field(default_factory=dict)
    connection_epoch: int | None = None
    sequence_gaps: int = 0
    messages: int = 0

    @staticmethod
    def _message(record: dict) -> dict | None:
        message = record.get("message")
        if isinstance(message, dict):
            return message
        raw_json = record.get("raw_json")
        if isinstance(raw_json, str):
            try:
                decoded = json.loads(raw_json)
            except json.JSONDecodeError:
                return None
            return decoded if isinstance(decoded, dict) else None
        return record if "type" in record else None

    def apply_record(self, record: dict) -> str | None:
        message = self._message(record)
        if message is None:
            return None
        body = message.get("msg", message)
        if not isinstance(body, dict):
            return None
        typ = message.get("type", body.get("type", ""))
        if typ not in {"orderbook_snapshot", "orderbook_delta"}:
            return None
        ticker = body.get("market_ticker")
        if not isinstance(ticker, str) or not ticker:
            return None

        epoch = int(record.get("connection_epoch", 0) or 0)
        if self.connection_epoch is None:
            self.connection_epoch = epoch
        elif epoch != self.connection_epoch:
            self.connection_epoch = epoch
            self.last_sequence.clear()
            for book in self.books.values():
                book.quarantined = True

        sid = str(message.get("sid", message.get("subscription_id", "")))
        stream = f"{epoch}:{sid}"
        seq = message.get("seq", body.get("seq", message.get("sequence")))
        if isinstance(seq, int):
            prior = self.last_sequence.get(stream)
            if prior is not None and seq <= prior:
                return None
            if prior is not None and seq > prior + 1:
                self.sequence_gaps += 1
                for book in self.books.values():
                    book.gaps += 1
                    book.quarantined = True
            self.last_sequence[stream] = seq

        book = self.books.setdefault(ticker, Book())
        if isinstance(seq, int) and prior is not None and seq > prior + 1:
            # The missing frame may have belonged to this newly observed
            # ticker. Do not apply its delta before a fresh snapshot.
            book.gaps = max(book.gaps, 1)
            book.quarantined = True
        book.apply(message, track_sequence=False)
        self.messages += 1
        return ticker

    def state_dict(self) -> dict:
        return {
            "version": "kalshi-orderbook-checkpoint-v1",
            "connection_epoch": self.connection_epoch,
            "last_sequence": dict(sorted(self.last_sequence.items())),
            "sequence_gaps": self.sequence_gaps,
            "messages": self.messages,
            "books": {ticker: self.books[ticker].to_dict()
                      for ticker in sorted(self.books)},
        }

    def checkpoint(self) -> dict:
        state = self.state_dict()
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
        return {**state, "state_sha256": hashlib.sha256(canonical.encode()).hexdigest()}

    @classmethod
    def from_checkpoint(cls, checkpoint: dict) -> "ReplayState":
        supplied = checkpoint.get("state_sha256")
        state = {key: value for key, value in checkpoint.items()
                 if key != "state_sha256"}
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        if supplied != expected:
            raise ValueError("checkpoint state_sha256 does not match contents")
        if state.get("version") != "kalshi-orderbook-checkpoint-v1":
            raise ValueError("unsupported checkpoint version")
        return cls(
            books={ticker: Book.from_dict(book)
                   for ticker, book in state.get("books", {}).items()},
            last_sequence={str(key): int(value)
                           for key, value in state.get("last_sequence", {}).items()},
            connection_epoch=state.get("connection_epoch"),
            sequence_gaps=int(state.get("sequence_gaps", 0)),
            messages=int(state.get("messages", 0)),
        )

def buy_yes(book: Book, quantity: float, fee_rate: float = 0.0) -> dict:
    """Consume asks represented by the complement of resting NO bids."""
    if book.quarantined:
        raise OrderBookQuarantined("order book has an unresolved sequence gap; resnapshot before filling")
    remaining = quantity; cost = 0.0; fills=[]
    for no_bid, available in sorted(book.no.items(), reverse=True):
        ask = 100 - no_bid
        take = min(remaining, available)
        if take <= 0: continue
        fills.append({"yes_price_cents": ask, "quantity": take}); cost += take * ask / 100; remaining -= take
        if remaining <= 1e-12: break
    gross = cost; fees = gross * fee_rate; return {"requested": quantity, "filled": quantity - remaining, "remaining": remaining, "gross_cost": gross, "fees": fees, "total_cost": gross + fees, "fills": fills}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--quantity",type=float,required=True); p.add_argument("--fee-rate",type=float,default=0.0); p.add_argument("--ticker"); p.add_argument("--checkpoint-in",type=Path); p.add_argument("--checkpoint-out",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    replay = ReplayState.from_checkpoint(json.loads(a.checkpoint_in.read_text())) if a.checkpoint_in else ReplayState()
    with a.input.open() as fh:
        for line in fh:
            if not line.strip(): continue
            replay.apply_record(json.loads(line))
    if a.checkpoint_out:
        a.checkpoint_out.parent.mkdir(parents=True, exist_ok=True)
        a.checkpoint_out.write_text(json.dumps(replay.checkpoint(), indent=2, sort_keys=True) + "\n")
    ticker = a.ticker
    if ticker is None and len(replay.books) == 1:
        ticker = next(iter(replay.books))
    if ticker is None or ticker not in replay.books:
        raise SystemExit("--ticker is required when the capture contains zero or multiple markets")
    book = replay.books[ticker]
    try:
        fill = buy_yes(book, a.quantity, a.fee_rate)
        quarantined = False
    except OrderBookQuarantined as exc:
        fill = {"requested": a.quantity, "filled": 0.0, "remaining": a.quantity,
                "gross_cost": 0.0, "fees": 0.0, "total_cost": 0.0, "fills": [],
                "reason": str(exc)}
        quarantined = True
    result={"messages":replay.messages,"market_ticker":ticker,"sequence_gaps":replay.sequence_gaps,"last_sequence_by_stream":replay.last_sequence,"quarantined":quarantined,"fill":fill}; a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result,sort_keys=True))
if __name__ == "__main__": main()
