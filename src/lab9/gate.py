"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)
    Also caught: duplicated (item, seed) rows, rows on seeds outside the manifest, metrics that
    differ from what the rows give (a hand-tuned number), non-boolean row scores, and a broken
    baseline (a gate comparing against a broken baseline decides nothing)."""
    problems: list[str] = []
    problems += _report_problems(pr, spec, "PR")
    problems += _report_problems(base, spec, "baseline", graded=False)
    problems += _same_grid(pr, base)
    problems += _same_slices(pr, base)
    if base_spec is not None:
        problems += ratchet(spec, base_spec)
    return problems


ROW_KEYS = {"item_id", "seed", "slices", "cost"}
SAFETY_COUNTS = {"secret_leak", "approval_bypass"}   # aggregated as counts in lab9.eval.aggregate


def _num_bad(v) -> bool:
    return isinstance(v, str) or (isinstance(v, float) and not math.isfinite(v))


def _graded_ids(spec: dict, rep: dict) -> list[str]:
    """Spec metrics scored per row by a grader (pass_rate, refund_amount_correct, ...)."""
    from lab9.graders import GRADERS
    in_rows = set().union(*(r.keys() for r in rep.get("rows") or [{}])) - ROW_KEYS
    return [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS or m["id"] in in_rows]


def _report_problems(rep: dict, spec: dict, who: str, graded: bool = True) -> list[str]:
    """Problems visible inside one report: broken numbers, broken graders, a wrong row grid."""
    out: list[str] = []
    rows, man = rep.get("rows") or [], rep.get("manifest") or {}
    out += [f"{who} metric {k}={v!r} is not a finite number"
            for k, v in (rep.get("metrics") or {}).items() if _num_bad(v)]
    if rep.get("evaluator_failures"):
        out.append(f"{who} has {len(rep['evaluator_failures'])} evaluator failure(s), "
                   f"first: {rep['evaluator_failures'][0]}")
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        out.append(f"{who} has {len(rows)} rows, manifest says {man.get('items')} items x "
                   f"{len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        out.append(f"{who} has duplicated (item, seed) rows: {dup[:5]}")
    stray = sorted({r.get("seed") for r in rows} - set(man.get("seeds") or []), key=str)
    if stray:
        out.append(f"{who} rows use seeds {stray} that are not in its manifest")
    items = {r.get("item_id") for r in rows}
    if rows and man.get("items") is not None and len(items) != man["items"]:
        out.append(f"{who} rows cover {len(items)} items, manifest says {man['items']}")
    if not graded:
        return out
    ids = _graded_ids(spec, rep)
    for m in ids:
        bad = [r for r in rows if not isinstance(r.get(m), bool)]
        if bad:
            out.append(f"{who} metric {m}: {len(bad)} row(s) without a boolean score "
                       f"(e.g. {bad[0].get('item_id')}@{bad[0].get('seed')}={bad[0].get(m)!r}); "
                       f"a crashed grader must not drop out of the mean")
    return out + _recomputed(rep, ids, who)


def _recomputed(rep: dict, ids: list[str], who: str) -> list[str]:
    """Metrics must be what the rows say. A hand-tuned number next to untouched rows is caught here."""
    rows, mets = rep.get("rows") or [], rep.get("metrics") or {}
    if not rows:
        return []
    calc: dict[str, float | int | None] = {}
    for m in ids:
        vals = [r[m] for r in rows if isinstance(r.get(m), bool)]
        calc[m] = sum(vals) if m in SAFETY_COUNTS else (sum(vals) / len(vals) if vals else None)
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        by_item.setdefault(r.get("item_id"), []).append(bool(r.get("pass_rate")))
    if "pass_rate" in ids:
        calc["pass_5"] = sum(all(v) for v in by_item.values()) / len(by_item)
        for key in mets:
            for name, fn in (("pass_at_", stats.pass_at_k), ("pass_hat_", stats.pass_hat_k)):
                k = key[len(name):]
                if key.startswith(name) and k.isdigit() and min(len(v) for v in by_item.values()) >= int(k):
                    est = [fn(len(v), sum(v), int(k)) for v in by_item.values()]
                    calc[key] = sum(est) / len(est)
    out = []
    for key, want in calc.items():
        got = mets.get(key)
        if key not in mets or want is None or got is None or _num_bad(got):
            continue                                    # missing / NaN are reported elsewhere
        # lab9.eval rounds to 4 decimals: allow that rounding, nothing more (0.8499 -> 0.85 is caught)
        if abs(float(got) - float(want)) > 5e-5 + 1e-12:
            out.append(f"{who} metric {key}={got} but its rows give {round(float(want), 4)}")
    return out


def _same_grid(pr: dict, base: dict) -> list[str]:
    """Same (item, seed) set and same seeds as the baseline: no cherry-picked seeds or items."""
    out: list[str] = []
    a = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows") or []}
    b = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if a != b:
        miss, extra = sorted(b - a, key=str), sorted(a - b, key=str)
        out.append(f"(item, seed) set differs from the baseline: {len(miss)} missing {miss[:4]}, "
                   f"{len(extra)} extra {extra[:4]}")
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    if sorted(pm.get("seeds") or []) != sorted(bm.get("seeds") or []):
        out.append(f"seeds {pm.get('seeds')} differ from the baseline's {bm.get('seeds')}")
    if pm.get("items") != bm.get("items"):
        out.append(f"manifest items {pm.get('items')} differ from the baseline's {bm.get('items')}")
    return out


def _slice_tags(rep: dict) -> tuple[dict, list]:
    tags: dict = {}
    mixed: list = []
    for r in rep.get("rows") or []:
        t = frozenset(r.get("slices") or [])
        if r.get("item_id") in tags and tags[r["item_id"]] != t:
            mixed.append(r["item_id"])
        tags.setdefault(r.get("item_id"), t)
    return tags, mixed


def _same_slices(pr: dict, base: dict) -> list[str]:
    """Slice tags come from labels, not from the PR: relabelling an item hides it from the slice gate."""
    a, mixed = _slice_tags(pr)
    b, _ = _slice_tags(base)
    out = [f"PR item {i} carries different slice tags on different seeds" for i in sorted(set(mixed), key=str)]
    out += [f"item {i} slices {sorted(a[i])} differ from the baseline's {sorted(b[i])}"
            for i in sorted(set(a) & set(b), key=str) if a[i] != b[i]]
    return out


def _loosened(th: dict, base_th: dict, where: str) -> list[str]:
    out: list[str] = []
    for key in ("max", "max_increase"):
        if key in base_th and (key not in th or th[key] > base_th[key]):
            out.append(f"{where}: {key} {base_th[key]} -> {th.get(key, 'removed')} (looser)")
    if "min" in base_th and ("min" not in th or th["min"] < base_th["min"]):
        out.append(f"{where}: min {base_th['min']} -> {th.get('min', 'removed')} (looser)")
    if base_th.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append(f"{where}: no_significant_drop dropped")
    return out


def ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval set => thresholds may only get stricter. check() only gets here when the PR's
    eval_set_sha equals the baseline's, so renaming eval_set_version does not escape the ratchet."""
    out: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        out.append(f"RATCHET eval_set_version {base_spec.get('eval_set_version')!r} -> "
                   f"{spec.get('eval_set_version')!r} on an unchanged eval set")
    for key in ("eval_set", "labels", "adversarial_pack", "seeds", "pass_k", "bootstrap"):
        if base_spec.get(key) != spec.get(key):
            out.append(f"RATCHET {key} changed: {base_spec.get(key)!r} -> {spec.get(key)!r}")
    now = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        m = now.get(bm["id"])
        if m is None:
            out.append(f"RATCHET metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            out.append(f"RATCHET metric {bm['id']} no longer blocking")
        if bm.get("kind") != m.get("kind"):
            out.append(f"RATCHET metric {bm['id']} kind {bm.get('kind')} -> {m.get('kind')}")
        out += [f"RATCHET metric {p}" for p in _loosened(m.get("threshold") or {}, bm.get("threshold") or {}, bm["id"])]
    now_sl = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        sid = f"slice:{bs.get('name')}/{bs.get('metric')}"
        s = now_sl.get((bs.get("name"), bs.get("metric")))
        if s is None:
            out.append(f"RATCHET {sid} removed")
            continue
        if bs.get("blocking") and not s.get("blocking"):
            out.append(f"RATCHET {sid} no longer blocking")
        out += [f"RATCHET {p}" for p in _loosened(s, bs, sid)]
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", f"{len(a)} item(s)"
        if val is None:
            verdict = "missing"                       # an empty slice proves nothing: never a pass
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        elif "max" in sl and val > sl["max"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and a:
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"{len(keys)} item(s) Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {sid:<44} {val!s:<8} {json.dumps(th):<48} {note:<38} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
