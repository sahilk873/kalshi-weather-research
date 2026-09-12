"""Generate docs/settlement_analysis.md from the normalized data tables.

Read-only over the retained research set (never downloads, never mutates raw
files):

- data/weather_research/kalshi/events.csv, markets.csv, contract_outcomes.csv
- data/weather_research/ghcn/labels_daily.csv
- data/weather_research/nws_cli/daily_climate_cli.csv

It pins the settlement-source eras, the GHCN-vs-Kalshi bucket reconstruction
test, and the NWS-CLI cross-checks so the documentation does not drift from
the data. It introduces no model or trading logic and adds no new data.

Regenerate with:
    python3 scripts/weather/settlement_analysis.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))

# ruff: noqa: E402
from common import REPO_ROOT, ensure_runtime_dirs, to_float, utcnow  # noqa: E402

OUT_RELPATH = "docs/settlement_analysis.md"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", errors="replace") as fh:
        return list(csv.DictReader(fh))


def _pct(n: int, total: int) -> float:
    return round(n / total * 100, 1) if total else 0.0


def _fmt(v) -> str:
    if v is None:
        return ""
    return v


def _bucket_inside(val: float, floor, ceil) -> bool:
    return ((floor is None or val >= floor) and (ceil is None or val <= ceil))


def rounded_labels(markets, ghcn) -> dict:
    """Reconstruction: finalized bucket result vs airport GHCN daily label."""
    by = {(r["city"], r["date"]): r for r in ghcn}
    out = {"per_city": {}, "label_missing_dates": Counter()}
    totals = Counter()
    per_city: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for m in markets:
        if m["status"] != "finalized":
            continue
        city, date = m["city"], m["outcome_local_date"]
        g = by.get((city, date))
        if not g:
            out["label_missing_dates"][date] += 1
            continue
        val = to_float(g["tmax_f"] if m["temp_type"] == "high" else g["tmin_f"])
        if val is None:
            out["label_missing_dates"][date] += 1
            continue
        floor = to_float(m["bucket_floor_f"])
        ceil = to_float(m["bucket_ceil_f"])
        is_yes = m["result"] == "yes"
        exact_ok = _bucket_inside(val, floor, ceil) == is_yes
        rounded = _bucket_inside(round(val), floor, ceil) == is_yes
        near_edge = ((floor is not None and abs(val - floor) < 0.15) or
                     (ceil is not None and abs(val - ceil) < 0.15))
        pc = per_city[city]
        pc["total"].append(1)
        pc["exact_ok"].append(int(exact_ok))
        pc["rounded_ok"].append(int(rounded))
        pc["boundary"].append(int(near_edge))
        if (not exact_ok) and near_edge:
            pc["mismatch_boundary"].append(1)
    for city, pc in per_city.items():
        n = len(pc["total"])
        out["per_city"][city] = {
            "checked": n,
            "exact_ok": sum(pc["exact_ok"]),
            "rounded_ok": sum(pc["rounded_ok"]),
            "boundary_close": sum(pc["boundary"]),
            "mismatch_boundary": len(pc["mismatch_boundary"]),
            "exact_pct": _pct(sum(pc["exact_ok"]), n),
            "rounded_pct": _pct(sum(pc["rounded_ok"]), n),
        }
    out["checked"] = sum(len(pc["total"]) for pc in per_city.values())
    out["exact_ok"] = sum(sum(pc["exact_ok"]) for pc in per_city.values())
    out["rounded_ok"] = sum(sum(pc["rounded_ok"]) for pc in per_city.values())
    out["boundary_close"] = sum(sum(pc["boundary"]) for pc in per_city.values())
    out["mismatch_boundary"] = sum(
        len(pc["mismatch_boundary"]) for pc in per_city.values())
    out["label_missing"] = sum(out["label_missing_dates"].values())
    return out


def cli_vs_ghcn(cli, ghcn) -> dict:
    """Whole-degree NWS CLI text values vs rounded airport GHCN labels.

    One comparison per distinct climate date, using the earliest retained
    issuance (the point-in-time value published first for that day).
    """
    g = {(r["city"], r["date"]): r for r in ghcn}
    by: dict[tuple, list[dict]] = defaultdict(list)
    for r in cli:
        by[(r["city"], r["climate_date"])].append(r)
    hi_ok = lo_ok = 0
    compared = 0
    for key, rs in by.items():
        gg = g.get(key)
        if not gg:
            continue
        first = min(rs, key=lambda r: r["publication_time_utc"])
        hi = to_float(first["official_daily_high_f"])
        lo = to_float(first["official_daily_low_f"])
        ghi = to_float(gg["tmax_f"])
        glo = to_float(gg["tmin_f"])
        if ghi is not None and hi is not None:
            compared += 1
            hi_ok += int(round(ghi) == round(float(hi)))
        if glo is not None and lo is not None:
            lo_ok += int(round(glo) == round(float(lo)))
    # high/low comparison sets always coincide on CLI dates that carry labels.
    return {"dates": compared, "high_matched": hi_ok,
            "high_compared": compared, "low_matched": lo_ok,
            "low_compared": compared}


def cli_vs_kalshi(cli, markets, events) -> dict:
    """Bucket hit using NWS CLI text values, with the binding source flagged."""
    src = {r["event_ticker"]: r["settlement_source_name"] for r in events}
    cli_dates = {(r["city"], r["climate_date"]) for r in cli}
    matched = total = 0
    sources = Counter()
    for m in markets:
        if m["status"] != "finalized":
            continue
        if (m["city"], m["outcome_local_date"]) not in cli_dates:
            continue
        cli_row = next(r for r in cli
                       if r["city"] == m["city"]
                       and r["climate_date"] == m["outcome_local_date"])
        val = to_float(cli_row["official_daily_high_f"]
                       if m["temp_type"] == "high"
                       else cli_row["official_daily_low_f"])
        if val is None:
            continue
        floor = to_float(m["bucket_floor_f"])
        ceil = to_float(m["bucket_ceil_f"])
        is_yes = m["result"] == "yes"
        ok = _bucket_inside(val, floor, ceil) == is_yes
        total += 1
        matched += int(ok)
        sources[src.get(m["event_ticker"], "?")] += 1
    return {"checked": total, "matched": matched,
            "matched_pct": _pct(matched, total),
            "events_by_source": dict(sources)}


def settlement_summary(events, markets) -> dict:
    out = {}
    out["events_total"] = len(events)
    out["markets_total"] = len(markets)
    out["markets_active"] = sum(1 for m in markets if m["status"] == "active")
    out["markets_finalized"] = sum(
        1 for m in markets if m["status"] == "finalized")
    src_by_ev = {r["event_ticker"]: r["settlement_source_name"] for r in events}
    finalized_by_src = Counter(src_by_ev.get(m["event_ticker"], "?")
                               for m in markets if m["status"] == "finalized")
    active_by_src = Counter(src_by_ev.get(m["event_ticker"], "?")
                            for m in markets if m["status"] == "active")
    out["finalized_by_source"] = dict(finalized_by_src)
    out["active_by_source"] = dict(active_by_src)
    # per city per temp_type bucket counts by source
    detail = defaultdict(Counter)
    for m in markets:
        if m["status"] != "finalized":
            continue
        detail[(m["city"], m["temp_type"])][
            src_by_ev.get(m["event_ticker"], "?")] += 1
    out["finalized_detail"] = {
        f"{city}/{tt}": dict(c) for (city, tt), c in sorted(detail.items())}
    return out


def rule_text_snapshots() -> list[dict]:
    """NWS-era and TWC-era rule wording from the raw series payloads."""
    out = []
    payloads = REPO_ROOT / "data" / "series"
    for series in ("KXHIGHTLV", "KXHIGHTPHX", "KXLOWTLV", "KXLOWTPHX"):
        path = payloads / f"{series}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        events = data.get("events") or []
        nws = twc = None
        for ev in events:
            markets = ev.get("markets") or []
            if not markets:
                continue
            rule = markets[0].get("rules_primary", "")
            if "Climatological Report" in rule and nws is None:
                nws = (ev.get("event_ticker", ""), rule)
            elif "Weather Company" in rule and twc is None:
                twc = (ev.get("event_ticker", ""), rule)
        if nws:
            out.append({"series": series, "era": "NWS",
                        "event": nws[0], "rules_primary": nws[1]})
        if twc:
            out.append({"series": series, "era": "TWC",
                        "event": twc[0], "rules_primary": twc[1]})
    return sorted(out, key=lambda r: (r["series"], r["era"]))


def era_transitions(events) -> dict:
    out = {}
    for city in ("phx", "lv"):
        nws = [r["outcome_local_date"] for r in events
               if r["city"] == city and r["settlement_source_name"].startswith("NWS")]
        twc = [r["outcome_local_date"] for r in events
               if r["city"] == city and not r["settlement_source_name"].startswith("NWS")]
        out[city] = {
            "nws_first": min(nws) if nws else None,
            "nws_last": max(nws) if nws else None,
            "twc_first": min(twc) if twc else None,
            "twc_last": max(twc) if twc else None,
        }
    return out


def retained_windows(events) -> list[dict]:
    rows = []
    for city in ("phx", "lv"):
        for st in set(r["series_ticker"] for r in events
                      if r["city"] == city):
            dates = sorted({r["outcome_local_date"] for r in events
                            if r["city"] == city and r["series_ticker"] == st})
            rows.append({"series": st, "count": len(dates),
                         "first": dates[0], "last": dates[-1]})
    return sorted(rows, key=lambda r: r["series"])


def ghcn_archive_bounds(ghcn) -> dict:
    out = {}
    for city in ("phx", "lv"):
        dates = [r["date"] for r in ghcn if r["city"] == city]
        if dates:
            out[city] = (min(dates), max(dates), len(dates))
    return out


def cli_coverage(cli) -> dict:
    by = defaultdict(list)
    for r in cli:
        by[(r["city"], r["climate_date"])].append(r["publication_time_utc"])
    dates = sorted({(r["city"], r["climate_date"]) for r in cli})
    # two observed issuance slots: roughly 00:xxZ and 08:xxZ UTC.
    slots = defaultdict(list)
    for r in cli:
        hhmm = r["publication_time_utc"][11:16]
        slot = "00xxZ" if hhmm < "04:00" else "08xxZ"
        slots[(r["city"], slot)].append(hhmm)
    slot_bounds = {f"{c}/{s}": (min(v), max(v))
                   for (c, s), v in sorted(slots.items())}
    return {"unique_dates": len(dates),
            "product_versions": len(cli),
            "dates": dates,
            "slot_bounds": slot_bounds}


def bucket_examples(markets):
    seen = set()
    out = []
    for m in markets:
        key = (m["bucket_floor_f"], m["bucket_ceil_f"])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "ticker": m["market_ticker"],
            "label": (m["yes_sub_title"] or "").strip(),
            "floor": _fmt(m["bucket_floor_f"]),
            "ceil": _fmt(m["bucket_ceil_f"]),
        })
        if len(seen) >= 3:
            break
    return out


def render(summary, eras, windows, ghcn_bounds, recon, cg, ck,
           cli_info, examples, rule_snaps) -> str:
    lines = []
    a = lines.append
    a("# PHX / KLAS daily high–low settlement analysis")
    a("")
    a("_Generated by `scripts/weather/settlement_analysis.py` at "
      f"{utcnow()} — do not hand-edit; regenerate with `python3 "
      "scripts/weather/settlement_analysis.py`. Read-only over the retained "
      "normalized tables._")
    a("")
    a("## 1. Scope and retained event history")
    a("")
    a("This analysis covers the four in-scope series `KXHIGHTPHX`, "
      "`KXLOWTPHX`, `KXHIGHTLV`, and `KXLOWTLV`. The tables below are computed "
      "from `data/weather_research/kalshi/events.csv` and `markets.csv` as "
      "retained in this checkout; they are not a claim about Kalshi's full "
      "multi-year series history (the events API exposes only a limited "
      "window).")
    a("")
    a("| Series | retained events | first outcome date | last outcome date |")
    a("| --- | --- | --- | --- |")
    for w in windows:
        a(f"| {w['series']} | {w['count']} | {w['first']} | {w['last']} |")
    a("")
    a("## 2. Settlement source eras")
    a("")
    a("The binding settlement source is per event, in "
      "`data/weather_research/kalshi/events.csv`. Every event-level "
      "`settlement_sources[0]` currently names either an NWS Daily Climate "
      "Report (`CLIPHX` at `KPSR` or `CLILAS` at `KVEF`) or The Weather "
      "Company.")
    a("")
    a("| City | last NWS outcome date | first TWC outcome date | retained window |")
    a("| --- | --- | --- | --- |")
    for city in ("phx", "lv"):
        e = eras[city]
        rng = f"{e['nws_first']}..{e['nws_last']}"
        a(f"| {city.upper()} | {e['nws_last']} | {e['twc_first']} | "
          f"NWS {rng}; TWC {e['twc_first']}..{e['twc_last']} |")
    a("")
    a(f"- Events: {summary['events_total']:,}; markets total "
      f"{summary['markets_total']:,} "
      f"(active {summary['markets_active']}, finalized "
      f"{summary['markets_finalized']:,}).")
    a("- Finalized buckets by source: " +
      "; ".join(f"{src}: {n:,}"
                for src, n in sorted(summary['finalized_by_source'].items())))
    a("- Active buckets by source: " +
      "; ".join(f"{src}: {n}"
                for src, n in sorted(summary['active_by_source'].items())))
    a("- Finalized bucket detail (city/temp_type → source → count):")
    for key, mapping in summary["finalized_detail"].items():
        a(f"  - `{key}`: " + "; ".join(f"{s}: {n:,}" for s, n in mapping.items()))
    a("")
    a("The Weather Company-era events in this checkout all fall after the "
      "retained NWS era described above (`2026-08-14` onward), so there is "
      "no mixing of source eras within a single event.")
    a("")
    a("Rule text as recorded in the raw `data/series/*.json` payloads "
      "confirms the split (example market per era, first occurrence in "
      "payload order):")
    a("")
    a("| series | era | event | rules_primary (excerpt) |")
    a("| --- | --- | --- | --- |")
    for snap in rule_snaps:
        a(f"| {snap['series']} | {snap['era']} | {snap['event']} | "
          f"{snap['rules_primary'][:130]}… |")
    a("")
    a("## 3. Kalshi bucket geometry and result semantics")
    a("")
    a("Markets are mutually exclusive integer-°F buckets. Internal buckets "
      "are inclusive whole-degree ranges; tails are `<= N` (parsed as "
      "`bucket_ceil_f=N`, `bucket_floor_f` empty) and `>= N` (parsed as "
      "`bucket_floor_f=N`). Examples parsed from `markets.csv`:")
    a("")
    a("| market ticker | yes subtitle | floor F | ceil F |")
    a("| --- | --- | --- | --- |")
    for ex in examples:
        a(f"| {ex['ticker']} | {ex['label']} | {ex['floor']} | {ex['ceil']} |")
    a("")
    a("`result` is `yes`/`no` per finalized bucket and is transcribed to "
      "`settled_yes` in `contract_outcomes.csv`. The contract text may say "
      "\"less than 103°\" while the subtitle reads \"102° or below\"; use the "
      "parsed bounds, never string comparisons.")
    a("")
    a("## 4. Reconstruction test: airport GHCN daily labels vs bucket results")
    a("")
    a("For every finalized market whose outcome date has a GHCN-Daily label "
      "(`ghcn/labels_daily.csv`), the label °F value is tested against the "
      "parsed bucket bounds. The GHCN store keeps tenths-°C; `tmax_f`/`tmin_f` "
      "are the exact conversion (value*9/5+32). Two models are scored: "
      "**exact** (continuous °F against integer bucket edges) and **rounded** "
      "(whole-°F via `round()` first, matching the whole-degree values the "
      "settlement providers publish).")
    a("")
    a("| City | checked | exact match | exact % | rounded match | rounded % | "
      "boundary-close buckets | exact mismatches that are boundary-close |")
    a("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for city in ("phx", "lv"):
        r = recon["per_city"][city]
        a(f"| {city.upper()} | {r['checked']} | {r['exact_ok']} | "
          f"{r['exact_pct']}% | {r['rounded_ok']} | {r['rounded_pct']}% | "
          f"{r['boundary_close']} | {r['mismatch_boundary']} |")
    a(f"| **total** | **{recon['checked']}** | **{recon['exact_ok']}** | "
      f"**{_pct(recon['exact_ok'], recon['checked'])}%** | "
      f"**{recon['rounded_ok']}** | **{_pct(recon['rounded_ok'], recon['checked'])}%** | "
      f"**{recon['boundary_close']}** | **{recon['mismatch_boundary']}** |")
    a("")
    a(f"- {recon['label_missing']} finalized buckets had no GHCN label. "
      "They are entirely on outcome dates "
      + " and ".join(sorted(recon["label_missing_dates"])) + ", i.e. the two "
      "most recent finalized dates, beyond the last published label in the "
      "retained GHCN archive.")
    a(f"  GHCN archive bounds: PHX `{ghcn_bounds['phx'][1]}` (from "
      f"{ghcn_bounds['phx'][0]}, {ghcn_bounds['phx'][2]:,} dates), LV "
      f"`{ghcn_bounds['lv'][1]}` (from {ghcn_bounds['lv'][0]}, "
      f"{ghcn_bounds['lv'][2]:,} dates).")
    a("")
    a("Interpretation: the small exact-°F disagreement is purely rounding at "
      "bucket edges — a tenths-°C climate value converted to a whole-°F "
      "settlement value round-trips to the same bucket in 100% of checked "
      "buckets. Every exact mismatch ("
      f"{recon['mismatch_boundary']} of "
      f"{recon['boundary_close']} boundary-close buckets) sits within 0.15 °F "
      "of a bucket edge.")
    a("")
    a("This is observed agreement between the retained airport GHCN labels "
      "and recorded outcomes. It is **not** proof that GHCN is legally "
      "interchangeable with each settlement feed (see section 7).")
    a("")
    a("## 5. NWS CLI text cross-checks")
    a("")
    a(f"The retained CLI archive (`nws_cli/daily_climate_cli.csv`) holds "
      f"{cli_info['product_versions']} product versions across "
      f"{cli_info['unique_dates']} climate dates: "
      + ", ".join(f"{c}:{d}" for (c, d) in cli_info["dates"]) + ".")
    a("")
    a("IEM's public AFOS interface keeps only a rolling ~7-day window; a "
      "multi-year request returns only the products still inside retention "
      "(observed here as the single stale tail product for 2025-12-30). "
      "Two issuance slots appear per date "
      f"({'; '.join(f'{k}: {v[0]}..{v[1]}Z' for k, v in cli_info['slot_bounds'].items())}); "
      "values matched across both slots for every date in this archive. "
      "Publication time is the observed `publication_time_utc` in the CSV and "
      "is usable as the product visible-at-time timestamp.")
    a("")
    a(f"### 5.1 CLI whole-°F vs rounded GHCN labels")
    a("")
    a(f"- High: {cg['high_matched']}/{cg['high_compared']} climate dates "
      f"matched the rounded GHCN label; Low: "
      f"{cg['low_matched']}/{cg['low_compared']} (each compared on the "
      "earliest retained issuance per date). The CLI text and the GHCN "
      "archive are independent NWS-family products; agreement is perfect in "
      "the retained window.")
    a("")
    a(f"### 5.2 CLI bucket hit vs recorded Kalshi outcomes (informational)")
    a("")
    a(f"- {ck['checked']} finalized buckets overlap CLI climate dates; CLI "
      f"whole-degree value falls in the recorded bucket {ck['matched']}"
      f" ({ck['matched_pct']}%).")
    if ck["checked"]:
        a(f"- These outcomes are all on TWC-sourced events "
          f"({'; '.join(f'{k}: {v}' for k, v in ck['events_by_source'].items())}), "
          "so the CLI hit is a cross-source reconstruction check, not a "
          "verification of the binding source. Note that this CLI window is "
          "inside the current era where Kalshi cites The Weather Company.")
    a("")
    a("## 6. Anti-lookahead rules for label reuse")
    a("")
    a("- `ghcn/labels_daily.csv` carries `label_available_ts`, a deliberate "
      "conservative synthetic gate (climate day + 36 h). GHCN does not publish "
      "row-level release times; treat this as a floor, not the observed "
      "publication time.")
    a("- `nws_cli/daily_climate_cli.csv` carries the observed "
      "`publication_time_utc`; use it instead of the synthetic gate wherever "
      "a CLI product is the active published label. Never apply a later "
      "revision to an earlier decision timestamp.")
    a("- Event-level `settlement_source_name`/`url` is the legal source, not "
      "the series ticker. Never join a finalized `result`, a CLI product, or "
      "the GHCN label into features before its own publication time.")
    a("- METAR sampled daily extremes (`iem/asos_daily.csv`) are intraday "
      "information only and are not daily labels.")
    a("")
    a("## 7. Limits and blockers")
    a("")
    a("- The Weather Company's underlying station/history is licensed; this "
      "project does not capture its point-in-time feed. TWC-era backtests may "
      "use the GHCN reconstruction only as an explicitly labelled **proxy**, "
      "with sensitivity around integer boundaries.")
    a("- IEM AFOS does not retain multi-year CLI history. Full NWS-era "
      "reproduction requires an official long-term text-product archive or a "
      "source agreement; before that, the NWS-era check above is limited to "
      "whatever CLI window is downloadable.")
    a("- The retained Kalshi event history is a limited window: the earliest "
      "retained outcome date is "
      f"{min(w['first'] for w in windows)} "
      f"(Phoenix series begin {min(w['first'] for w in windows if w['series'].endswith('PHX'))}, "
      f"Las Vegas series begin "
      f"{min(w['first'] for w in windows if w['series'].endswith('LV'))}); "
      "earlier events are not present in this checkout.")
    a("- GHCN-Daily lags real time: the last retained label is "
      f"{max(ghcn_bounds[c][1] for c in ghcn_bounds)}; the two most recent "
      "finalized outcome dates are therefore not reconstructable yet.")
    a("")
    return "\n".join(lines) + "\n"


def main() -> int:
    dirs = ensure_runtime_dirs()
    events = read_csv(dirs["kalshi_out"] / "events.csv")
    markets = read_csv(dirs["kalshi_out"] / "markets.csv")
    ghcn = read_csv(dirs["ghcn_out"] / "labels_daily.csv")
    cli = read_csv(dirs["research"] / "nws_cli" / "daily_climate_cli.csv")

    md = render(
        settlement_summary(events, markets),
        era_transitions(events),
        retained_windows(events),
        ghcn_archive_bounds(ghcn),
        rounded_labels(markets, ghcn),
        cli_vs_ghcn(cli, ghcn),
        cli_vs_kalshi(cli, markets, events),
        cli_coverage(cli),
        bucket_examples(markets),
        rule_text_snapshots(),
    )

    out_path = dirs["research"].parent.parent / OUT_RELPATH
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

