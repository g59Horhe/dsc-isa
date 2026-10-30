"""Summarise the clock sweep (make sweep): one row per configuration and target,
then the Xpulp clock-period penalty under several statistics.

Usage: python3 sweep_table.py build/sweep [--csv out.csv] [--stats-csv out.csv]
                              [--floor base:10-11.5,pulp:11-13.5]

Achieved period = target - worst setup slack, with the propagated clock. The
_GRT columns use global-route parasitics (before any GRT_REPAIR; wns_grtrep
is the slack after it); the _RCX columns (sweeps run through
detailed routing with RCX_RULES) use parasitics extracted from the detailed
routes. A target closes when the worst slack is >= 0. skew_ns is from the last
report_clock_skew in the log (the extracted one when present).

Penalty statistics, for each parasitics source present in every finished row:
  shortest achieved period at any target;
  floor median: the median period over the floor targets, by default every
    target tighter than that core's shortest achieved period (the targets the
    repair tool cannot reach), or the ranges given with --floor;
  floor pairs: the range of penalties over every pairing of a base floor point
    with an Xpulp floor point;
  shortest and median period among closed points, and the tightest closed target.
"""
import csv, os, re, statistics, sys

def grab(text, key):
    m = re.search(key + r' (-?[\d.]+)', text)
    return float(m.group(1)) if m else None

def skew(text):
    # the last report_clock_skew block: "latency  CRPR  skew" on its final line
    # (2022 build), or "<skew> setup skew" (26Q2, signed, worst path's pair)
    blocks = re.findall(r'Latency\s+CRPR\s+Skew\n(?:.*\n)*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d.]+)\n'
                        r'|\n\s*(-?[\d.]+) setup skew\n', text)
    if not blocks:
        return None
    return float(blocks[-1][2] or blocks[-1][3])

def rows(root):
    out = []
    for d in sorted(os.listdir(root)):
        m = re.fullmatch(r'(base|pulp)-([\d.]+)', d)
        if not m:
            continue
        f = os.path.join(root, d, 'openroad.txt')
        text = open(f).read() if os.path.exists(f) else ''
        target = float(m.group(2))
        area = re.findall(r'Design area (\d+) um?\^2 (\d+)% utilization', text)
        r = dict(cfg=m.group(1), target_ns=target)
        for src in ('GRT', 'RCX'):
            wns = grab(text, 'WORST_SLACK_' + src)
            s = src.lower()
            r['wns_' + s] = wns
            r['period_' + s] = None if wns is None else round(target - wns, 3)
            r['closed_' + s] = None if wns is None else wns >= 0
            r['hold_' + s] = grab(text, 'WORST_HOLD_' + src)
            r['tns_' + s] = grab(text, 'TNS_' + src)
        # GRT_REPAIR=1 runs: global-route slack after the post-route repair
        r['wns_grtrep'] = grab(text, 'WORST_SLACK_GRTREP')
        drc = grab(text, 'DRC_VIOLATIONS')
        drt = grab(text, 'DRT_SECONDS')
        r.update(drc=None if drc is None else int(drc), drt_s=None if drt is None else int(drt),
                 skew_ns=skew(text), placed_ns=grab(text, 'WORST_SLACK_PLACED'),
                 cts_ns=grab(text, 'WORST_SLACK_CTS'),
                 area_um2=int(area[-1][0]) if area else None,
                 error='ERROR' in text or 'Error:' in text)
        out.append(r)
    return sorted(out, key=lambda r: (r['cfg'], r['target_ns']))

def parse_floor(spec):
    # "base:10-11.5,pulp:11-13.5" -> {'base': (10.0, 11.5), 'pulp': (11.0, 13.5)}
    out = {}
    for part in spec.split(','):
        cfg, rng = part.split(':')
        lo, hi = rng.split('-')
        out[cfg] = (float(lo), float(hi))
    return out

def pct(p, b):
    return 100 * (p / b - 1)

def stats(rs, src, floor=None):
    """Penalty statistics on the period_<src> column; None if any row lacks it."""
    key, closed = 'period_' + src, 'closed_' + src
    pts = {c: [r for r in rs if r['cfg'] == c] for c in ('base', 'pulp')}
    if not all(pts.values()) or any(r[key] is None for c in pts for r in pts[c]):
        return None
    out, fl = [], {}
    best = {c: min(r[key] for r in pts[c]) for c in pts}
    out.append(('shortest achieved period, any target', best['base'], best['pulp']))
    for c in pts:
        if floor:
            lo, hi = floor[c]
            fl[c] = [r for r in pts[c] if lo <= r['target_ns'] <= hi]
        else:
            fl[c] = [r for r in pts[c] if r['target_ns'] < best[c]]
    rng = lambda c: f"{min(r['target_ns'] for r in fl[c]):g} to {max(r['target_ns'] for r in fl[c]):g}"
    how = 'given' if floor else 'targets below the shortest period'
    out.append((f'median of the floor targets ({how}: base {rng("base")}, Xpulp {rng("pulp")})',
                statistics.median(r[key] for r in fl['base']),
                statistics.median(r[key] for r in fl['pulp'])))
    cl = {c: [r for r in pts[c] if r[closed]] for c in pts}
    if all(cl.values()):
        out.append(('shortest period among closed points',
                    min(r[key] for r in cl['base']), min(r[key] for r in cl['pulp'])))
        out.append(('median period among closed points',
                    statistics.median(r[key] for r in cl['base']),
                    statistics.median(r[key] for r in cl['pulp'])))
        out.append(('tightest closed target',
                    min(r['target_ns'] for r in cl['base']), min(r['target_ns'] for r in cl['pulp'])))
    else:
        none = ' and '.join(c for c in cl if not cl[c])
        print(f'\n{src.upper()}: no closed points for {none}; closed-point statistics omitted')
    pairs = [pct(p[key], b[key]) for b in fl['base'] for p in fl['pulp']]
    spread = {c: (min(r[key] for r in fl[c]), max(r[key] for r in fl[c])) for c in fl}
    return out, (min(pairs), max(pairs), len(pairs)), spread

def main():
    root = sys.argv[1]
    rs = rows(root)
    floor = parse_floor(sys.argv[sys.argv.index('--floor') + 1]) if '--floor' in sys.argv else None
    has_rcx = any(r['wns_rcx'] is not None for r in rs)
    keys = ['cfg', 'target_ns', 'wns_grt', 'period_grt', 'closed_grt']
    if any(r['wns_grtrep'] is not None for r in rs):
        keys += ['wns_grtrep']
    if has_rcx:
        keys += ['wns_rcx', 'period_rcx', 'closed_rcx', 'hold_rcx', 'tns_rcx', 'drc', 'drt_s']
    else:
        keys += ['hold_grt', 'tns_grt']
    keys += ['skew_ns', 'area_um2', 'error']
    print(' '.join(f'{k:>10s}' for k in keys))
    for r in rs:
        print(' '.join(f'{"" if r[k] is None else str(r[k]):>10s}' for k in keys))
    srows = []
    for src, label in (('grt', 'global-route parasitics'), ('rcx', 'extracted parasitics')):
        s = stats(rs, src, floor)
        if s is None:
            if src == 'rcx' and has_rcx:
                print(f'\n{label}: not every point has finished; no statistics')
            continue
        st, (lo, hi, n), spread = s
        print(f'\nPenalty, {label} ({root})\n')
        print('| statistic | base (ns) | Xpulp (ns) | penalty |')
        print('|---|---|---|---|')
        for name, b, p in st:
            print(f'| {name} | {b:g} | {p:g} | {pct(p, b):+.1f}% |')
            srows.append(dict(parasitics=src, statistic=name, base_ns=round(b, 4), pulp_ns=round(p, 4),
                              penalty_pct=round(pct(p, b), 2)))
        print(f'\nfloor periods: base {spread["base"][0]:g} to {spread["base"][1]:g} ns, '
              f'Xpulp {spread["pulp"][0]:g} to {spread["pulp"][1]:g} ns; '
              f'{n} floor pairs give penalties {lo:+.1f}% to {hi:+.1f}%')
        srows.append(dict(parasitics=src, statistic='floor pairs, lowest', base_ns=None, pulp_ns=None,
                          penalty_pct=round(lo, 2)))
        srows.append(dict(parasitics=src, statistic='floor pairs, highest', base_ns=None, pulp_ns=None,
                          penalty_pct=round(hi, 2)))
    if '--csv' in sys.argv:
        with open(sys.argv[sys.argv.index('--csv') + 1], 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0].keys()))
            w.writeheader(); w.writerows(rs)
    if '--stats-csv' in sys.argv and srows:
        with open(sys.argv[sys.argv.index('--stats-csv') + 1], 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(srows[0].keys()))
            w.writeheader(); w.writerows(srows)

if __name__ == '__main__':
    main()
