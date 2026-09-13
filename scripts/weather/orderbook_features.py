"""Extract deterministic microstructure features from replayed order books."""
from __future__ import annotations
from datetime import datetime, timezone
import argparse, csv, json
from pathlib import Path
from replay_orderbook import Book

def features(book, received_ts: str = "", close_ts: str = "") -> dict[str, float | str]:
    yes = sorted(book.yes.items(), reverse=True); no = sorted(book.no.items(), reverse=True)
    best_yes = yes[0][0] if yes else None; best_no = no[0][0] if no else None
    bid = float(best_yes) if best_yes is not None else float("nan")
    ask = float(100 - best_no) if best_no is not None else float("nan")
    bid_depth = float(yes[0][1]) if yes else 0.0; ask_depth = float(no[0][1]) if no else 0.0
    total = bid_depth + ask_depth
    out = {"received_ts": received_ts, "best_yes_bid_cents": bid, "best_yes_ask_cents": ask, "spread_cents": ask - bid if yes and no else float("nan"), "top_depth": total, "imbalance": (bid_depth - ask_depth) / total if total else float("nan"), "sequence_gaps": float(book.gaps)}
    if close_ts:
        try: out["minutes_to_close"] = (_parse(close_ts) - _parse(received_ts)).total_seconds() / 60
        except (ValueError, TypeError): out["minutes_to_close"] = float("nan")
    return out

def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    books: dict[str, Book] = {}; rows=[]; global_last_seq = None; global_gaps = 0
    with a.input.open() as fh:
        for line in fh:
            if not line.strip(): continue
            record=json.loads(line); received=record.get("received_ts", ""); message=record.get("message", record)
            body=message.get("msg", message); ticker=body.get("market_ticker", "")
            if not ticker: continue
            book=books.setdefault(ticker, Book())
            seq=message.get("seq", body.get("seq", message.get("sequence")))
            if isinstance(seq, int):
                if global_last_seq is not None and seq > global_last_seq + 1: global_gaps += 1
                if global_last_seq is not None and seq <= global_last_seq: continue
                global_last_seq=seq
            book.apply(message, track_sequence=False)
            row=features(book,received); row["market_ticker"] = ticker; row["sequence_gaps"] = float(global_gaps); rows.append(row)
    fields=["market_ticker","received_ts","best_yes_bid_cents","best_yes_ask_cents","spread_cents","top_depth","imbalance","sequence_gaps"]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="") as fh: w=csv.DictWriter(fh,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"wrote {a.output} ({len(rows)} rows)")

if __name__ == "__main__": main()
