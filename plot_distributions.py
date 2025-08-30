import argparse
import glob
import os
from datetime import datetime

import pandas as pd
import numpy as np

try:
    import seaborn as sns  # type: ignore
    HAS_SEABORN = True
except Exception:
    HAS_SEABORN = False

import matplotlib.pyplot as plt


def find_default_csv() -> str | None:
    candidates = sorted(
        glob.glob("espn_projections_*_season.csv"),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    return candidates[0] if candidates else None


def coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def sanitize_positions(df: pd.DataFrame) -> pd.DataFrame:
    # Keep only rows with a position and numeric projected_points
    df = df.copy()
    if "projected_points" in df.columns:
        df["projected_points"] = coerce_numeric(df["projected_points"]).fillna(0.0)
    df = df[df["position"].notna()]
    return df


def infer_season_from_filename(path: str) -> str | None:
    base = os.path.basename(path)
    # Expect espn_projections_YYYY_season.csv
    parts = base.split("_")
    for i, token in enumerate(parts):
        if token.isdigit() and len(token) == 4:
            return token
    return None


def _gaussian_kernel(sigma_bins: float) -> np.ndarray:
    sigma = max(1e-6, float(sigma_bins))
    radius = int(max(3, round(3 * sigma)))
    xs = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-0.5 * (xs / sigma) ** 2)
    k /= k.sum() if k.sum() != 0 else 1.0
    return k


def plot_position_distribution(
    df: pd.DataFrame,
    position: str,
    out_dir: str,
    season: str | None,
    bins: str | int = "auto",
    clip_quantile: float = 0.995,
    kde: bool = True,
    min_points: float = 150.0,
    smooth_sigma: float = 2.5,
    bw_adjust: float = 1.0,
) -> str:
    data = df[df["position"] == position]["projected_points"].dropna()
    # Apply threshold filter
    data = data[data > min_points]
    if data.empty:
        return ""

    os.makedirs(out_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))

    upper = data.quantile(clip_quantile) if 0 < clip_quantile < 1 else data.max()
    lower = max(0.0, data.min())
    plot_data = data.clip(lower=lower, upper=upper)

    title_season = f" {season}" if season else ""
    title = f"Projected Points Distribution - {position}{title_season}"

    if HAS_SEABORN:
        sns.set_style("whitegrid")
        if kde:
            sns.kdeplot(plot_data, ax=ax, color="#4C78A8", fill=True, alpha=0.25, bw_adjust=bw_adjust)
        sns.histplot(plot_data, bins=bins, stat="density", ax=ax, color="#4C78A8", alpha=0.35)
    else:
        # Histogram + Gaussian smoothing fallback
        if isinstance(bins, str):
            bins_n = max(50, min(200, int(np.sqrt(len(plot_data)))))
        else:
            bins_n = int(bins)
        counts, edges = np.histogram(plot_data.values, bins=bins_n, density=True)
        centers = 0.5 * (edges[:-1] + edges[1:])
        if kde and smooth_sigma and smooth_sigma > 0:
            kernel = _gaussian_kernel(smooth_sigma)
            counts = np.convolve(counts, kernel, mode="same")
        ax.plot(centers, counts, color="#4C78A8", linewidth=1.8)
        ax.fill_between(centers, 0, counts, color="#4C78A8", alpha=0.18)

    mean_val = plot_data.mean()
    median_val = plot_data.median()
    ax.axvline(mean_val, color="#E45756", linestyle="--", linewidth=1.2, label=f"Mean: {mean_val:.1f}")
    ax.axvline(median_val, color="#72B7B2", linestyle=":", linewidth=1.2, label=f"Median: {median_val:.1f}")

    ax.set_title(title)
    ax.set_xlabel("Projected Points")
    ax.set_ylabel("Density")
    ax.legend()
    # Start x-axis at the threshold
    ax.set_xlim(left=min_points)
    ax.grid(True, linestyle=":", alpha=0.5)

    ts = datetime.now().strftime("%Y%m%d")
    safe_pos = position.replace("/", "-")
    season_tag = season or "season"
    out_path = os.path.join(out_dir, f"dist_{season_tag}_{safe_pos}_{ts}.png")
    fig.tight_layout()
    fig.savefig(out_path, dpi=144)
    plt.close(fig)
    return out_path


def plot_overlay_distribution(
    df: pd.DataFrame,
    out_dir: str,
    season: str | None,
    bins: int | None = None,
    clip_quantile: float = 0.995,
    kde: bool = True,
    min_points: float = 150.0,
    smooth_sigma: float = 2.5,
    bw_adjust: float = 1.0,
) -> str:
    # Prepare data
    df = df.copy()
    df = df[["position", "projected_points"]].dropna()
    df["projected_points"] = coerce_numeric(df["projected_points"]).fillna(0.0)
    # Apply threshold filter globally
    df = df[df["projected_points"] > min_points]

    # Compute global clip so overlays share an x-limits
    upper = df["projected_points"].quantile(clip_quantile) if 0 < clip_quantile < 1 else df["projected_points"].max()
    lower = float(min_points)
    df["projected_points"] = df["projected_points"].clip(lower=lower, upper=upper)

    # Keep common fantasy positions first
    preferred_order = ["QB", "RB", "WR", "TE", "K", "DST"]
    order = [p for p in preferred_order if p in df["position"].unique().tolist()]
    for p in df["position"].unique():
        if p not in order:
            order.append(p)

    os.makedirs(out_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))

    title_season = f" {season}" if season else ""
    ax.set_title(f"Projected Points Distributions by Position{title_season}")
    ax.set_xlabel("Projected Points")
    ax.set_ylabel("Density")

    if HAS_SEABORN and kde:
        sns.set_style("whitegrid")
        sns.kdeplot(
            data=df,
            x="projected_points",
            hue="position",
            hue_order=order,
            common_norm=False,
            multiple="layer",
            fill=True,
            alpha=0.25,
            bw_adjust=bw_adjust,
            linewidth=1.5,
            ax=ax,
        )
    else:
        # Fallback: shared-bin histogram density smoothed visually by line + fill
        colors = plt.get_cmap("tab10")
        # Choose bins if not provided
        if bins is None:
            # rule-of-thumb bins
            bins = max(50, min(200, int(np.sqrt(len(df)))))
        xs = np.linspace(lower, upper, bins + 1)
        centers = 0.5 * (xs[:-1] + xs[1:])
        kernel = _gaussian_kernel(smooth_sigma) if kde and smooth_sigma and smooth_sigma > 0 else None
        for i, pos in enumerate(order):
            vals = df.loc[df["position"] == pos, "projected_points"].values
            if len(vals) == 0:
                continue
            hist, _ = np.histogram(vals, bins=xs, density=True)
            if kernel is not None:
                hist = np.convolve(hist, kernel, mode="same")
            c = colors(i % 10)
            ax.plot(centers, hist, color=c, label=pos, linewidth=1.8)
            ax.fill_between(centers, 0, hist, color=c, alpha=0.18)

    ax.set_xlim(left=lower, right=upper)
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(title="Position")
    fig.tight_layout()

    ts = datetime.now().strftime("%Y%m%d")
    season_tag = season or "season"
    out_path = os.path.join(out_dir, f"overlay_{season_tag}_{ts}.png")
    fig.savefig(out_path, dpi=144)
    plt.close(fig)
    return out_path


def plot_all_positions(
    csv_path: str,
    out_dir: str,
    bins: str | int = "auto",
    clip_quantile: float = 0.995,
    kde: bool = True,
    min_points: float = 150.0,
    smooth_sigma: float = 2.5,
    bw_adjust: float = 1.0,
) -> list[str]:
    df = pd.read_csv(csv_path)
    if not {"position", "projected_points"}.issubset(df.columns):
        raise SystemExit("CSV must contain 'position' and 'projected_points' columns")

    df = sanitize_positions(df)
    # Apply threshold filter once
    df = df[df["projected_points"] > min_points]
    season = infer_season_from_filename(csv_path)

    # Keep only common fantasy positions; preserve CSV’s positions order
    preferred_order = ["QB", "RB", "WR", "TE", "K", "DST"]
    positions = [p for p in preferred_order if p in df["position"].unique().tolist()]
    # Include any unknown positions at the end
    for p in df["position"].unique():
        if p not in positions:
            positions.append(p)

    outputs: list[str] = []
    for pos in positions:
        path = plot_position_distribution(
            df,
            pos,
            out_dir=out_dir,
            season=season,
            bins=bins,
            clip_quantile=clip_quantile,
            kde=kde,
            min_points=min_points,
            smooth_sigma=smooth_sigma,
            bw_adjust=bw_adjust,
        )
        if path:
            outputs.append(path)
    return outputs


def main():
    parser = argparse.ArgumentParser(description="Plot projected points distributions by position")
    parser.add_argument(
        "--input",
        dest="input_csv",
        default=None,
        help="Path to CSV from espn_projections.py (defaults to latest espn_projections_*_season.csv)",
    )
    parser.add_argument(
        "--out",
        dest="out_dir",
        default="charts",
        help="Directory to write charts (default: charts)",
    )
    parser.add_argument(
        "--bins",
        dest="bins",
        default="auto",
        help="Histogram bins (int or 'auto', default: auto)",
    )
    parser.add_argument(
        "--clip-quantile",
        dest="clip_quantile",
        type=float,
        default=0.995,
        help="Upper quantile to clip x-axis (0..1, default: 0.995)",
    )
    parser.add_argument(
        "--no-kde",
        dest="no_kde",
        action="store_true",
        help="Disable KDE overlay",
    )
    parser.add_argument(
        "--min-points",
        dest="min_points",
        type=float,
        default=150.0,
        help="Minimum projected points to include (default: 150)",
    )
    parser.add_argument(
        "--smooth-sigma",
        dest="smooth_sigma",
        type=float,
        default=2.5,
        help="Gaussian smoothing in bin units for fallback renderer (default: 2.5)",
    )
    parser.add_argument(
        "--bw-adjust",
        dest="bw_adjust",
        type=float,
        default=1.0,
        help="Seaborn KDE bandwidth adjust (smaller = smoother, default: 1.0)",
    )
    parser.add_argument(
        "--overlay-only",
        dest="overlay_only",
        action="store_true",
        help="Create a single overlay chart instead of per-position charts",
    )

    args = parser.parse_args()
    input_csv = args.input_csv or find_default_csv()
    if not input_csv or not os.path.exists(input_csv):
        raise SystemExit("Could not find input CSV. Run espn_projections.py first or pass --input.")

    # Convert bins to int if numeric
    bins: str | int
    try:
        bins = int(args.bins)
    except Exception:
        bins = str(args.bins)

    # Load once
    df = pd.read_csv(input_csv)
    if not {"position", "projected_points"}.issubset(df.columns):
        raise SystemExit("CSV must contain 'position' and 'projected_points' columns")
    df = sanitize_positions(df)
    season = infer_season_from_filename(input_csv)

    outputs: list[str] = []
    # Overlay chart (default behavior now)
    out_overlay = plot_overlay_distribution(
        df,
        out_dir=args.out_dir,
        season=season,
        bins=(None if isinstance(bins, str) else int(bins)),
        clip_quantile=args.clip_quantile,
        kde=(not args.no_kde),
        min_points=args.min_points,
        smooth_sigma=args.smooth_sigma,
        bw_adjust=args.bw_adjust,
    )
    outputs.append(out_overlay)

    # Optional separate charts as well
    if not args.overlay_only:
        sep_outputs = plot_all_positions(
            csv_path=input_csv,
            out_dir=args.out_dir,
            bins=(bins if isinstance(bins, (int,)) else "auto"),
            clip_quantile=args.clip_quantile,
            kde=(not args.no_kde),
            min_points=args.min_points,
            smooth_sigma=args.smooth_sigma,
            bw_adjust=args.bw_adjust,
        )
        outputs.extend(sep_outputs)

    print(f"Wrote {len(outputs)} chart(s) to {args.out_dir}")
    for p in outputs:
        print(p)


if __name__ == "__main__":
    main()
