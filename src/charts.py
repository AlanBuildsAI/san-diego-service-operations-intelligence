"""Inline-SVG chart primitives for the static dashboard.

Charts are emitted as SVG written against CSS custom properties, so the same
markup renders correctly in light and dark mode without a second palette.

Colour discipline — two series slots carry meaning consistently across every
chart in the dashboard:

    --series-1 (blue)   typical / recent / within threshold
    --series-2 (orange) tail / aged / duplicated

Nothing is coloured decoratively. Where only one series is present there is no
legend; where two are present a legend is always shown, so identity is never
carried by colour alone.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

# Geometry defaults, in SVG user units.
BAR_RADIUS = 4
LINE_WIDTH = 2
MARKER_RADIUS = 5


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _fmt(value: float, decimals: int = 0) -> str:
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def _clip(text: str, max_chars: int) -> str:
    """Truncate a category label; the full string stays in the mark's tooltip."""
    text = str(text)
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def nice_ticks(scale_max: float, target: int = 4) -> list[float]:
    """Round tick values at or below scale_max.

    Axis ticks read as reference points, so they must be numbers a person would
    choose (5,000 / 10,000), not arbitrary fractions of the series maximum.
    """
    if scale_max <= 0:
        return [0.0]
    raw = scale_max / target
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if raw <= step:
            break
    ticks, value = [], step
    while value <= scale_max * 1.0001:
        ticks.append(value)
        value += step
    return ticks or [scale_max]


@dataclass
class Series:
    label: str
    values: list[float]
    slot: str = "var(--series-1)"


def legend(entries: list[tuple[str, str]]) -> str:
    """Legend row. Always rendered when a chart carries two or more series."""
    items = "".join(
        f'<span class="lg-item"><span class="lg-swatch" style="background:{color}"></span>'
        f'<span class="lg-label">{esc(label)}</span></span>'
        for label, color in entries
    )
    return f'<div class="legend">{items}</div>'


def horizontal_bars(
    labels: list[str],
    primary: list[float],
    secondary: list[float] | None = None,
    *,
    primary_label: str = "",
    secondary_label: str = "",
    value_suffix: str = "",
    width: int = 720,
    row_height: int = 30,
    label_width: int = 210,
    value_width: int = 78,
    decimals: int = 0,
) -> str:
    """Horizontal bars, optionally stacked into two meaningful segments.

    Stacked segments are separated by a 2px surface gap so the boundary reads as
    a division rather than a colour change.
    """
    secondary = secondary or [0.0] * len(labels)
    totals = [p + s for p, s in zip(primary, secondary)]
    scale_max = max(totals) if totals else 1
    plot_width = width - label_width - value_width
    height = row_height * len(labels) + 8

    rows = []
    for i, label in enumerate(labels):
        y = i * row_height + 4
        bar_y = y + 5
        bar_h = row_height - 14
        p_w = (primary[i] / scale_max) * plot_width if scale_max else 0
        s_w = (secondary[i] / scale_max) * plot_width if scale_max else 0
        gap = 2 if (p_w > 0 and s_w > 0) else 0

        rows.append(
            f'<text class="ax-label" x="{label_width - 10}" y="{bar_y + bar_h / 2 + 4}" '
            f'text-anchor="end">{esc(_clip(label, max(int(label_width / 7.2), 12)))}'
            f'<title>{esc(label)}</title></text>'
        )
        if p_w > 0:
            rows.append(
                f'<rect x="{label_width}" y="{bar_y}" width="{max(p_w - gap, 1):.2f}" '
                f'height="{bar_h}" rx="{BAR_RADIUS}" fill="var(--series-1)">'
                f'<title>{esc(label)} — {esc(primary_label or "value")}: '
                f'{_fmt(primary[i], decimals)}{esc(value_suffix)}</title></rect>'
            )
        if s_w > 0:
            rows.append(
                f'<rect x="{label_width + p_w:.2f}" y="{bar_y}" width="{max(s_w, 1):.2f}" '
                f'height="{bar_h}" rx="{BAR_RADIUS}" fill="var(--series-2)">'
                f'<title>{esc(label)} — {esc(secondary_label or "value")}: '
                f'{_fmt(secondary[i], decimals)}{esc(value_suffix)}</title></rect>'
            )
        rows.append(
            f'<text class="ax-value" x="{width - 8}" y="{bar_y + bar_h / 2 + 4}" '
            f'text-anchor="end">{_fmt(totals[i], decimals)}{esc(value_suffix)}</text>'
        )

    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMinYMin meet">{"".join(rows)}</svg>'
    )


def vertical_bars(
    labels: list[str],
    values: list[float],
    colors: list[str],
    *,
    width: int = 720,
    height: int = 260,
    value_suffix: str = "",
    decimals: int = 0,
) -> str:
    """Vertical bars for an ordered categorical axis (aging buckets)."""
    pad_left, pad_right, pad_top, pad_bottom = 52, 12, 26, 42
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    scale_max = max(values) if values else 1
    slot = plot_w / len(labels)
    bar_w = min(slot * 0.62, 68)

    parts = []
    # Recessive gridlines at round values, not fractions of the series maximum.
    ticks = nice_ticks(scale_max)
    axis_max = max(ticks[-1], scale_max)
    for tick in ticks:
        y = pad_top + plot_h * (1 - tick / axis_max)
        parts.append(
            f'<line class="grid" x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="ax-tick" x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end">'
            f'{_fmt(tick)}</text>'
        )

    for i, (label, value, color) in enumerate(zip(labels, values, colors)):
        cx = pad_left + slot * i + slot / 2
        bar_h = (value / axis_max) * plot_h if axis_max else 0
        y = pad_top + plot_h - bar_h
        parts.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(bar_h, 1):.1f}" rx="{BAR_RADIUS}" fill="{color}">'
            f'<title>{esc(label)} days: {_fmt(value, decimals)}{esc(value_suffix)}</title></rect>'
        )
        parts.append(
            f'<text class="ax-value" x="{cx:.1f}" y="{y - 7:.1f}" text-anchor="middle">'
            f'{_fmt(value, decimals)}{esc(value_suffix)}</text>'
        )
        parts.append(
            f'<text class="ax-label" x="{cx:.1f}" y="{height - 22}" text-anchor="middle">'
            f'{esc(label)}</text>'
        )

    parts.append(
        f'<line class="axis" x1="{pad_left}" y1="{pad_top + plot_h}" '
        f'x2="{width - pad_right}" y2="{pad_top + plot_h}"/>'
    )
    parts.append(
        f'<text class="ax-caption" x="{pad_left + plot_w / 2}" y="{height - 4}" '
        f'text-anchor="middle">Active request age (days)</text>'
    )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMinYMin meet">{"".join(parts)}</svg>'
    )


def dumbbell(
    labels: list[str],
    low: list[float],
    high: list[float],
    *,
    width: int = 720,
    row_height: int = 30,
    label_width: int = 210,
    low_label: str = "Median",
    high_label: str = "P90",
) -> str:
    """Median-to-p90 dumbbell: one row per category, connector shows the spread."""
    scale_max = max(high) if high else 1
    value_width = 118            # room for "1,296 / 2,710" without touching a marker
    plot_w = width - label_width - value_width
    height = row_height * len(labels) + 12

    parts = []
    for i, label in enumerate(labels):
        y = i * row_height + 20
        x_low = label_width + (low[i] / scale_max) * plot_w
        x_high = label_width + (high[i] / scale_max) * plot_w
        parts.append(
            f'<text class="ax-label" x="{label_width - 10}" y="{y + 4}" '
            f'text-anchor="end">{esc(_clip(label, max(int(label_width / 7.2), 12)))}'
            f'<title>{esc(label)}</title></text>'
        )
        parts.append(
            f'<line class="connector" x1="{x_low:.1f}" y1="{y}" x2="{x_high:.1f}" y2="{y}"/>'
        )
        parts.append(
            f'<circle cx="{x_low:.1f}" cy="{y}" r="{MARKER_RADIUS}" fill="var(--series-1)" '
            f'stroke="var(--surface-1)" stroke-width="2">'
            f'<title>{esc(label)} — {esc(low_label)}: {_fmt(low[i])} days</title></circle>'
        )
        parts.append(
            f'<circle cx="{x_high:.1f}" cy="{y}" r="{MARKER_RADIUS}" fill="var(--series-2)" '
            f'stroke="var(--surface-1)" stroke-width="2">'
            f'<title>{esc(label)} — {esc(high_label)}: {_fmt(high[i])} days</title></circle>'
        )
        parts.append(
            f'<text class="ax-value" x="{width - 8}" y="{y + 4}" text-anchor="end">'
            f'{_fmt(low[i])} / {_fmt(high[i])}</text>'
        )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMinYMin meet">{"".join(parts)}</svg>'
    )


def index_lollipop(
    labels: list[str],
    values: list[float],
    *,
    baseline: float = 1.0,
    width: int = 560,
    row_height: int = 30,
    label_width: int = 110,
) -> str:
    """Deviation-from-baseline lollipop for a unit-free index."""
    lo = min(min(values), baseline) * 0.97
    hi = max(max(values), baseline) * 1.03
    span = hi - lo or 1
    plot_w = width - label_width - 56
    height = row_height * len(labels) + 26

    def x_of(v: float) -> float:
        return label_width + ((v - lo) / span) * plot_w

    x_base = x_of(baseline)
    parts = [
        f'<line class="axis" x1="{x_base:.1f}" y1="14" x2="{x_base:.1f}" '
        f'y2="{height - 18}" stroke-dasharray="3 3"/>',
        f'<text class="ax-caption" x="{x_base:.1f}" y="{height - 4}" text-anchor="middle">'
        f'1.00 = city average</text>',
    ]
    for i, (label, value) in enumerate(zip(labels, values)):
        y = i * row_height + 24
        x = x_of(value)
        color = "var(--series-2)" if value >= baseline else "var(--series-1)"
        parts.append(
            f'<text class="ax-label" x="{label_width - 10}" y="{y + 4}" '
            f'text-anchor="end">{esc(label)}</text>'
        )
        parts.append(
            f'<line class="connector" x1="{x_base:.1f}" y1="{y}" x2="{x:.1f}" y2="{y}"/>'
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y}" r="{MARKER_RADIUS}" fill="{color}" '
            f'stroke="var(--surface-1)" stroke-width="2">'
            f'<title>{esc(label)}: index {value:.3f}</title></circle>'
        )
        parts.append(
            f'<text class="ax-value" x="{width - 6}" y="{y + 4}" text-anchor="end">'
            f'{value:.3f}</text>'
        )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMinYMin meet">{"".join(parts)}</svg>'
    )


def line_chart(
    x_labels: list[str],
    values: list[float],
    complete_flags: list[bool],
    *,
    width: int = 720,
    height: int = 250,
) -> str:
    """Monthly series. Incomplete months render dashed and hollow, never as a drop."""
    pad_left, pad_right, pad_top, pad_bottom = 56, 14, 22, 46
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    vmax = max(values) * 1.08 if values else 1
    vmin = 0.0
    step = plot_w / max(len(values) - 1, 1)

    def pt(i: int, v: float) -> tuple[float, float]:
        return pad_left + i * step, pad_top + plot_h - ((v - vmin) / (vmax - vmin)) * plot_h

    parts = []
    for tick in nice_ticks(vmax):
        y = pad_top + plot_h * (1 - tick / vmax)
        parts.append(f'<line class="grid" x1="{pad_left}" y1="{y:.1f}" '
                     f'x2="{width - pad_right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="ax-tick" x="{pad_left - 8}" y="{y + 4:.1f}" '
                     f'text-anchor="end">{_fmt(tick)}</text>')

    last_complete = max((i for i, c in enumerate(complete_flags) if c), default=0)
    solid = [pt(i, v) for i, v in enumerate(values) if i <= last_complete]
    dashed = [pt(i, v) for i, v in enumerate(values) if i >= last_complete]

    if len(solid) > 1:
        d = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(solid))
        parts.append(f'<path d="{d}" fill="none" stroke="var(--series-1)" '
                     f'stroke-width="{LINE_WIDTH}" stroke-linejoin="round"/>')
    if len(dashed) > 1:
        d = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(dashed))
        parts.append(f'<path d="{d}" fill="none" stroke="var(--series-1)" '
                     f'stroke-width="{LINE_WIDTH}" stroke-dasharray="5 4" opacity="0.55"/>')

    for i, (label, value, complete) in enumerate(zip(x_labels, values, complete_flags)):
        x, y = pt(i, value)
        fill = "var(--series-1)" if complete else "var(--surface-1)"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{fill}" '
            f'stroke="var(--series-1)" stroke-width="2">'
            f'<title>{esc(label)}: {_fmt(value)} submissions'
            f'{"" if complete else " (month incomplete at snapshot)"}</title></circle>'
        )
        if i % 3 == 0 or i == len(values) - 1:
            parts.append(
                f'<text class="ax-label" x="{x:.1f}" y="{height - 24}" '
                f'text-anchor="middle">{esc(label)}</text>'
            )

    parts.append(f'<line class="axis" x1="{pad_left}" y1="{pad_top + plot_h}" '
                 f'x2="{width - pad_right}" y2="{pad_top + plot_h}"/>')
    parts.append(f'<text class="ax-caption" x="{pad_left + plot_w / 2}" y="{height - 5}" '
                 f'text-anchor="middle">Submission month — hollow marker = month '
                 f'incomplete at snapshot</text>')
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMinYMin meet">{"".join(parts)}</svg>'
    )
