from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use('Agg')

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

SUPPORTED_CHART_TYPES = {'line', 'bar', 'scatter', 'histogram', 'box', 'heatmap', 'control', 'spc', 'pareto'}


def render_matplotlib_chart(
    df: pd.DataFrame,
    *,
    chart_type: str,
    x: str,
    y: str,
    title: str,
    output_path: Path,
    thumb_path: Path,
    facet: str = '',
    color: str = '',
    dpi: int = 120,
) -> dict[str, Any]:
    """Render a manufacturing chart from the full DataFrame without downsampling."""
    normalized_type = chart_type.lower().strip()
    if normalized_type not in SUPPORTED_CHART_TYPES:
        raise ValueError(f'Unsupported chart_type: {chart_type}')

    _require_columns(df, [column for column in [x, y, color, facet] if column])

    fig, ax = plt.subplots(figsize=(16, 9), dpi=dpi)
    try:
        if normalized_type == 'line':
            _render_line(ax, df, x, y)
        elif normalized_type == 'scatter':
            _render_scatter(ax, df, x, y, color)
        elif normalized_type == 'bar':
            _render_bar(ax, df, x, y)
        elif normalized_type == 'histogram':
            _render_histogram(ax, df, y)
        elif normalized_type == 'box':
            _render_box(ax, df, x, y)
        elif normalized_type == 'heatmap':
            _render_heatmap(fig, ax, df, x, y, color)
        elif normalized_type in {'control', 'spc'}:
            _render_control(ax, df, x, y)
        elif normalized_type == 'pareto':
            _render_pareto(fig, ax, df, x, y)

        ax.set_title(title)
        if normalized_type not in {'histogram'}:
            ax.set_xlabel(x)
        if normalized_type not in {'heatmap'}:
            ax.set_ylabel(y)
        _format_datetime_axis(ax, df, x)
        fig.tight_layout()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
    finally:
        plt.close(fig)

    _write_thumbnail(output_path, thumb_path)
    return {
        'chart_type': normalized_type,
        'image_size_bytes': output_path.stat().st_size,
        'thumb_size_bytes': thumb_path.stat().st_size,
        'raw_row_count': int(len(df)),
    }


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f'Unknown column(s): {", ".join(missing)}')


def _render_line(ax, df: pd.DataFrame, x: str, y: str) -> None:
    ordered = df.sort_values(x)
    ax.plot(ordered[x], ordered[y], linewidth=1.5, rasterized=len(ordered) > 100_000)


def _render_scatter(ax, df: pd.DataFrame, x: str, y: str, color: str) -> None:
    kwargs: dict[str, Any] = {'s': 16 if len(df) < 100_000 else 4, 'alpha': 0.75, 'rasterized': len(df) > 100_000}
    if color and pd.api.types.is_numeric_dtype(df[color]):
        kwargs['c'] = df[color]
        kwargs['cmap'] = 'viridis'
        scatter = ax.scatter(df[x], df[y], **kwargs)
        plt.colorbar(scatter, ax=ax, label=color)
    else:
        ax.scatter(df[x], df[y], **kwargs)


def _render_bar(ax, df: pd.DataFrame, x: str, y: str) -> None:
    values = df.groupby(x, dropna=False)[y].mean(numeric_only=True).sort_values(ascending=False)
    ax.bar(values.index.astype(str), values.values)
    ax.tick_params(axis='x', rotation=35)


def _render_histogram(ax, df: pd.DataFrame, y: str) -> None:
    ax.hist(pd.to_numeric(df[y], errors='coerce').dropna(), bins='auto')
    ax.set_xlabel(y)
    ax.set_ylabel('count')


def _render_box(ax, df: pd.DataFrame, x: str, y: str) -> None:
    grouped = [
        pd.to_numeric(group[y], errors='coerce').dropna().to_numpy()
        for _, group in df.groupby(x, dropna=False)
    ]
    labels = [str(key) for key, _ in df.groupby(x, dropna=False)]
    ax.boxplot(grouped, tick_labels=labels, showmeans=True)
    ax.tick_params(axis='x', rotation=35)


def _render_heatmap(fig, ax, df: pd.DataFrame, x: str, y: str, color: str) -> None:
    if color:
        pivot = df.pivot_table(index=y, columns=x, values=color, aggfunc='mean')
    else:
        pivot = pd.crosstab(df[y], df[x])
    image = ax.imshow(pivot.to_numpy(), aspect='auto', interpolation='nearest', cmap='viridis')
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([str(value) for value in pivot.columns], rotation=35, ha='right')
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(value) for value in pivot.index])
    fig.colorbar(image, ax=ax, label=color or 'count')


def _render_control(ax, df: pd.DataFrame, x: str, y: str) -> None:
    ordered = df.sort_values(x)
    values = pd.to_numeric(ordered[y], errors='coerce')
    ax.plot(ordered[x], values, linewidth=1.5, marker='o' if len(ordered) < 200 else None, rasterized=len(ordered) > 100_000)

    mean = float(values.mean())
    sigma = float(values.std(ddof=1)) if len(values.dropna()) > 1 else 0.0
    target = _first_numeric_column_value(ordered, 'spec_target') or mean
    usl = _first_numeric_column_value(ordered, 'spec_usl') or mean + 3 * sigma
    lsl = _first_numeric_column_value(ordered, 'spec_lsl') or mean - 3 * sigma

    ax.axhline(target, color='#2f6f4e', linestyle='-', linewidth=1.2, label='target/mean')
    ax.axhline(usl, color='#a33a3a', linestyle='--', linewidth=1.2, label='USL / +3sigma')
    ax.axhline(lsl, color='#a33a3a', linestyle='--', linewidth=1.2, label='LSL / -3sigma')
    ax.legend(loc='best')


def _render_pareto(fig, ax, df: pd.DataFrame, x: str, y: str) -> None:
    values = df.groupby(x, dropna=False)[y].sum(numeric_only=True).sort_values(ascending=False)
    cumulative = values.cumsum() / values.sum() * 100 if values.sum() else values.cumsum()
    ax.bar(values.index.astype(str), values.values)
    ax.tick_params(axis='x', rotation=35)
    ax.set_ylabel(y)
    ax2 = ax.twinx()
    ax2.plot(values.index.astype(str), cumulative.values, color='#a33a3a', marker='o')
    ax2.axhline(80, color='#555555', linestyle='--', linewidth=1)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel('cumulative %')
    fig.tight_layout()


def _first_numeric_column_value(df: pd.DataFrame, column: str) -> float | None:
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors='coerce').dropna()
    if values.empty:
        return None
    return float(values.iloc[0])


def _format_datetime_axis(ax, df: pd.DataFrame, x: str) -> None:
    if x in df.columns and pd.api.types.is_datetime64_any_dtype(df[x]):
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))


def _write_thumbnail(output_path: Path, thumb_path: Path) -> None:
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(output_path) as image:
        image.thumbnail((320, 180))
        image.save(thumb_path, format='PNG')
