"""Deterministic zero-dependency SVGs generated from the same audit input."""
from __future__ import annotations
from html import escape
from pathlib import Path
from .core import Profile, audit, clamped_sample


def coverage_svg(ref: Profile, comp: Profile, path: str | Path) -> None:
    result = audit(ref, comp)
    width, height = 1040, 420
    x0, x1 = ref.x[0], ref.x[-1]
    low = min((*ref.values, *comp.values)); high = max((*ref.values, *comp.values))
    if high == low:
        high = low + 1
    def xx(x: float, offset: int) -> float: return offset + 30 + (x - x0) / max(1e-12, x1 - x0) * 430
    def yy(y: float) -> float: return 340 - (y - low) / (high - low) * 240
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             '<title id="title">Truncated CFD profile yields zero clamped RMSE but incomplete coverage</title>',
             '<desc id="desc">Naive endpoint clamping on the left hides eight unsupported reference samples. Strict coverage audit on the right shades the missing region.</desc>',
             '<rect width="1040" height="420" fill="#f8fafc"/>',
             '<style>text{font:16px system-ui,sans-serif;fill:#1e293b}.muted{fill:#52637b;font-size:13px}.label{font-weight:700;font-size:19px}.ref{fill:none;stroke:#155e75;stroke-width:3}.calc{fill:none;stroke:#d97706;stroke-width:3}.pt{fill:#155e75}</style>']
    for offset, title, subtitle in [(0, 'Naive endpoint clamp', 'RMSE = 0 (misleading)'), (520, 'Coverage-aware audit', f'{result["supported_reference_samples"]}/{result["reference_samples"]} supported · full-domain FAIL')]:
        parts += [f'<text x="{offset+30}" y="45" class="label">{escape(title)}</text>',
                  f'<text x="{offset+30}" y="75">{escape(subtitle)}</text>',
                  f'<path d="M{offset+30} 100V340H{offset+460}" fill="none" stroke="#94a3b8"/>']
        if offset:
            xa = max(ref.x[0], comp.x[-1]); xb = ref.x[-1]
            if xb > xa:
                parts.append(f'<rect x="{xx(xa,offset):.2f}" y="100" width="{xx(xb,offset)-xx(xa,offset):.2f}" height="240" fill="#fed7aa" opacity="0.75"/>')
                parts.append(f'<text x="{xx(xa,offset)+8:.1f}" y="125" class="muted">no support</text>')
        def line(coords, vals, cls):
            points=' '.join(f'{xx(a,offset):.1f},{yy(b):.1f}' for a,b in zip(coords,vals))
            parts.append(f'<polyline class="{cls}" points="{points}"/>')
        line(ref.x,ref.values,'ref')
        if offset == 0:
            line(ref.x,[clamped_sample(comp,x) for x in ref.x],'calc')
        else:
            line(comp.x,comp.values,'calc')
        for x,y in zip(ref.x,ref.values):
            parts.append(f'<circle class="pt" cx="{xx(x,offset):.2f}" cy="{yy(y):.2f}" r="3"/>')
        parts.append(f'<text x="{offset+30}" y="375" class="muted">Reference samples: teal · computed: amber</text>')
    parts.append('</svg>')
    Path(path).write_text('\n'.join(parts)+'\n',encoding='utf-8')


def nasa_svg(per_station: dict[str, dict[float, float]], path: str | Path) -> None:
    """Plot normalized per-station MAE from derived A09 values (not solver output)."""
    stations=sorted(per_station['SA'])
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 410" role="img" aria-label="Mach 2.05 derived normalized MAE by station: SA compared with SST">',
           '<rect width="840" height="410" fill="#f8fafc"/>',
           '<text x="50" y="40" style="font:bold 22px system-ui;fill:#1e293b">Mach 2.05 duct · derived station MAE/U∞</text>',
           '<text x="50" y="67" style="font:14px system-ui;fill:#475569">SA vs SST, 10 exported stations; reconstructed from A09 per-station metrics</text>',
           '<path d="M50 90V330H795" stroke="#64748b" fill="none"/>']
    values=[v for d in per_station.values() for v in d.values()]
    top=max(values)*1.12
    def px(i):return 80+i*72
    def py(v):return 330-v/top*220
    for name,color in [('SA','#155e75'),('SST','#d97706')]:
        points=' '.join(f'{px(i):.2f},{py(per_station[name][x]):.2f}' for i,x in enumerate(stations))
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>')
        for i,x in enumerate(stations):parts.append(f'<circle cx="{px(i):.2f}" cy="{py(per_station[name][x]):.2f}" r="4" fill="{color}"/>')
    for i,x in enumerate(stations):parts.append(f'<text x="{px(i)-11}" y="351" style="font:12px system-ui;fill:#475569">{x:g}</text>')
    parts+=['<text x="355" y="383" style="font:14px system-ui;fill:#475569">Station x (mm)</text>',
            '<text x="620" y="95" style="font:14px system-ui;fill:#155e75">● SA</text>',
            '<text x="680" y="95" style="font:14px system-ui;fill:#d97706">● SST</text>','</svg>']
    Path(path).write_text('\n'.join(parts)+'\n',encoding='utf-8')
