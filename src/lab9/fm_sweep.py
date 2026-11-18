"""Evidence for docs/failure_taxonomy.md: turn on ONE bug switch at a time (on top of the `fixed`
agent) and list the eval items it breaks, with the graders that see it.

    python -m lab9.fm_sweep                                   # every switch, v1 eval set
    python -m lab9.fm_sweep --bugs stale_clause misreport     # a subset
    python -m lab9.fm_sweep --trace stale_clause C-006 11     # trace of one probe trial (lab9.trace_case)

Probe shapes are named `probe_<switch>` and registered in memory only: lab9/variants.py and
src/lab8/ are not touched, and the gate never sees these shapes.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from lab8.console import utf8_stdio
from lab9.eval import SPEC, load_spec, run_eval
from lab9.graders import GRADERS
from lab9.variant_agent import BENIGN, BUGS, make_shape

SAFETY = {"secret_leak", "approval_bypass"}
FM_OF = {"leaky_trace": "FM-01", "ignore_denied": "FM-02", "ticket_trust": "FM-03", "quiet_override": "FM-03",
         "sum_parts": "FM-04", "round_down": "FM-04", "pre_deducted": "FM-05", "stale_clause": "FM-06",
         "sibling_refund": "FM-07", "misreport": "FM-08"}


def register(bugs: list[str]) -> list[str]:
    from lab8.shapes import SHAPES
    names = []
    for b in bugs:
        SHAPES.setdefault(f"probe_{b}", make_shape(f"probe_{b}", {"no_override", b}))
        names.append(f"probe_{b}")
    return names


def sweep(spec: dict, bugs: list[str]) -> None:
    ids = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS]
    for b, shape in zip(bugs, register(bugs)):
        rep = run_eval(shape, spec)
        broken: dict[tuple[str, tuple[str, ...]], list[int]] = {}
        for r in rep["rows"]:
            flags = tuple(m for m in ids if (r[m] is True if m in SAFETY else r[m] is False))
            if flags:
                broken.setdefault((r["item_id"], flags), []).append(r["seed"])
        print(f"== {b} ({FM_OF.get(b, '?')}): pass_rate {rep['metrics']['pass_rate']}")
        for (item, flags), seeds in sorted(broken.items()):
            print(f"   {item} seeds {seeds}: {', '.join(flags)}")
        if not broken:
            print("   (no item breaks)")


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.fm_sweep")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--bugs", nargs="*", default=sorted(BUGS - BENIGN))
    ap.add_argument("--trace", nargs=3, metavar=("SWITCH", "CLAIM", "SEED"))
    args = ap.parse_args(argv)
    if args.trace:
        from lab9 import trace_case
        switch, claim, seed = args.trace
        register([switch])
        return trace_case.main(["--shape", f"probe_{switch}", "--claim", claim, "--seed", seed])
    sweep(load_spec(Path(args.spec)), args.bugs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
