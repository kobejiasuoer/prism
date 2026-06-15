#!/usr/bin/env python3
"""
Build Historical Edge Sample Pool

Constructs a large sample pool of (code, trade_date, features, labels) tuples
from historical data. This pool is used for similarity matching when computing
historical edge for new candidates.

Expected output:
- ~500k samples (500 codes × 1000 days)
- File: data/prism_data/cache/historical_edge_sample_pool.json
- Size: ~50-100 MB
- Runtime: 1-2 hours

Stage 3 research-only component - never affects readiness/scoring.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages"))

from screener.historical_edge.feature_builder import extract_features
from screener.historical_edge.label_builder import compute_labels


def get_stock_universe(root: Path) -> list[str]:
    """Get list of stock codes to process.

    Priority order:
    1. Discovery cache (most recent candidates)
    2. Fallback to bars.daily dataset
    3. Fallback to hardcoded universe
    """
    # Try discovery cache first
    discovery_cache = root / "cache" / "discovery_candidates.json"
    if discovery_cache.exists():
        try:
            with open(discovery_cache) as f:
                data = json.load(f)
                codes = [c["code"] for c in data.get("candidates", [])]
                if codes:
                    print(f"📊 Loaded {len(codes)} codes from discovery cache")
                    return codes
        except Exception as e:
            print(f"⚠️  Failed to load discovery cache: {e}")

    # Fallback: collect codes from bars.daily dataset snapshots
    print("⚠️  Discovery cache not found, scanning bars.daily snapshots")

    dataset_root = root / "datasets" / "bars.daily"
    if dataset_root.exists():
        codes_set = set()
        snapshot_count = 0

        for snapshot_dir in sorted(dataset_root.iterdir()):
            if not snapshot_dir.is_dir():
                continue

            snapshot_count += 1
            # Sample every 10th snapshot to speed up
            if snapshot_count % 10 != 0:
                continue

            for json_file in snapshot_dir.glob("*.json"):
                if json_file.stem.endswith(".manifest"):
                    continue
                # Filename is the stock code
                code = json_file.stem
                if code and len(code) == 6 and code.isdigit():
                    codes_set.add(code)

        if codes_set:
            codes = sorted(codes_set)
            print(f"📊 Found {len(codes)} codes from bars.daily snapshots")
            return codes[:500]  # Cap at 500 for reasonable runtime

    # Ultimate fallback: hardcoded list of major stocks
    print("⚠️  Using hardcoded fallback list")
    return [
        "600519", "600036", "601318", "600276", "600887",  # Top caps
        "000001", "000002", "000858", "000333", "000651",  # Shenzhen
    ]


def get_historical_dates(
    root: Path,
    lookback_days: int = 1200,
) -> list[str]:
    """Get list of historical trading dates to process.

    Args:
        root: Data warehouse root
        lookback_days: How many calendar days to look back (default 1200 ≈ 3.5 years)

    Returns:
        Sorted list of trade dates in YYYY-MM-DD format
    """
    try:
        # Load trade calendar from datasets (actual name is "trade_calendar" not "trade_calendar.info")
        calendar_dir = root / "datasets" / "trade_calendar"
        if not calendar_dir.exists():
            raise ValueError("trade_calendar dataset not found")

        # Find the latest snapshot
        snapshots = sorted([d.name for d in calendar_dir.iterdir() if d.is_dir()])
        if not snapshots:
            raise ValueError("No snapshots in trade_calendar")

        latest_snapshot = snapshots[-1]
        calendar_file = calendar_dir / latest_snapshot / "formal-calendar.json"

        if not calendar_file.exists():
            raise ValueError(f"Calendar file not found: {calendar_file}")

        # Load and parse calendar
        with open(calendar_file) as f:
            calendar_data = json.load(f)

        # The calendar file only has today's date - need to collect from multiple snapshots
        all_dates_set = set()

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # Scan all snapshots to collect trading dates
        for snapshot_dir in calendar_dir.iterdir():
            if not snapshot_dir.is_dir():
                continue

            snapshot_name = snapshot_dir.name
            if snapshot_name < start_date or snapshot_name > end_date:
                continue

            cal_file = snapshot_dir / "formal-calendar.json"
            if not cal_file.exists():
                continue

            try:
                with open(cal_file) as f:
                    entries = json.load(f)
                    for entry in entries:
                        if entry.get("is_open") or entry.get("is_open_raw") == 1:
                            trade_date = entry.get("trade_date")
                            if trade_date and start_date <= trade_date <= end_date:
                                all_dates_set.add(trade_date)
            except Exception:
                continue

        trading_dates = sorted(all_dates_set)

        if not trading_dates:
            raise ValueError("No trading dates found in range")

        print(f"📅 Found {len(trading_dates)} trading dates from {trading_dates[0]} to {trading_dates[-1]}")
        return trading_dates

    except Exception as e:
        print(f"❌ Failed to load trade calendar: {e}")
        sys.exit(1)


def build_sample(
    code: str,
    trade_date: str,
    root: Path,
) -> tuple[str, str, dict[str, Any], dict[str, Any]] | None:
    """Build a single sample (features + labels).

    Returns:
        (code, trade_date, features, labels) or None if extraction failed
    """
    try:
        # Extract features (T-1 data)
        features = extract_features(code, trade_date)
        if not features:
            return None

        # Compute labels (T+N forward returns)
        labels = compute_labels(code, trade_date)
        if not labels:
            return None

        # Skip if too many constraint violations (low-quality sample)
        constraint_count = sum([
            labels.get("limit_hit_t1", False),
            labels.get("suspension_t1_to_t5", False),
            labels.get("st_flagged", False),
            labels.get("extreme_vol_surge", False),
        ])
        if constraint_count >= 2:
            return None  # Too constrained, not a clean sample

        return (code, trade_date, features, labels)

    except Exception:
        # Silently skip - expected for samples with missing data
        return None


def save_checkpoint(samples: list, checkpoint_path: Path) -> None:
    """Save intermediate checkpoint."""
    try:
        with open(checkpoint_path, 'w') as f:
            json.dump(samples, f, ensure_ascii=False)
        print(f"💾 Checkpoint saved: {len(samples)} samples")
    except Exception as e:
        print(f"⚠️  Failed to save checkpoint: {e}")


def main() -> None:
    """Build the sample pool."""
    print("=" * 60)
    print("🏗️  Building Historical Edge Sample Pool")
    print("=" * 60)

    # Setup paths
    root = Path(__file__).parent.parent.parent / "data" / "prism_data"
    output_dir = root / "cache"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "historical_edge_sample_pool.json"
    checkpoint_path = output_dir / "historical_edge_sample_pool.checkpoint.json"

    # Load existing checkpoint if available
    samples = []
    processed_keys = set()

    if checkpoint_path.exists():
        try:
            with open(checkpoint_path) as f:
                samples = json.load(f)
                processed_keys = {(s[0], s[1]) for s in samples}
            print(f"📂 Loaded checkpoint: {len(samples)} existing samples")
        except Exception as e:
            print(f"⚠️  Failed to load checkpoint: {e}")

    # Get stock universe and date range
    codes = get_stock_universe(root)
    dates = get_historical_dates(root, lookback_days=1200)

    total_tasks = len(codes) * len(dates)
    print(f"\n📋 Processing: {len(codes)} codes × {len(dates)} dates = {total_tasks:,} samples")
    print(f"⏱️  Estimated runtime: {total_tasks / 300 / 60:.1f} hours (at ~300 samples/min)")
    print()

    # Build samples
    processed = len(samples)
    errors = 0
    start_time = datetime.now()
    checkpoint_interval = 10000  # Save every 10k samples

    for i, code in enumerate(codes, 1):
        for j, trade_date in enumerate(dates, 1):
            # Skip if already processed
            if (code, trade_date) in processed_keys:
                continue

            # Build sample
            sample = build_sample(code, trade_date, root)

            if sample:
                samples.append(sample)
                processed += 1

                # Progress report every 1000 samples
                if processed % 1000 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta_seconds = (total_tasks - processed) / rate if rate > 0 else 0
                    eta_hours = eta_seconds / 3600

                    print(
                        f"Progress: {processed:,}/{total_tasks:,} ({100*processed/total_tasks:.1f}%) | "
                        f"Rate: {rate:.0f}/min | "
                        f"ETA: {eta_hours:.1f}h | "
                        f"Code: {code} ({i}/{len(codes)})"
                    )

                # Save checkpoint
                if processed % checkpoint_interval == 0:
                    save_checkpoint(samples, checkpoint_path)
            else:
                errors += 1

        # Checkpoint after each code
        if processed % checkpoint_interval >= checkpoint_interval - len(dates):
            save_checkpoint(samples, checkpoint_path)

    # Final save
    print("\n" + "=" * 60)
    print("💾 Saving final output...")

    try:
        with open(output_path, 'w') as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"✅ Sample pool built successfully!")
        print()
        print(f"📊 Statistics:")
        print(f"   - Total samples: {len(samples):,}")
        print(f"   - Unique codes: {len({s[0] for s in samples}):,}")
        print(f"   - Date range: {min(s[1] for s in samples)} to {max(s[1] for s in samples)}")
        print(f"   - File size: {file_size_mb:.1f} MB")
        print(f"   - Runtime: {elapsed/3600:.2f} hours")
        print(f"   - Success rate: {100*len(samples)/(len(samples)+errors):.1f}%")
        print()
        print(f"📁 Output: {output_path}")
        print()
        print("🎯 Next steps:")
        print("   1. Validate on real candidates")
        print("   2. Compute actual quintiles from this pool")
        print("   3. Integrate into ai_screening.py")

        # Clean up checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            print(f"   🗑️  Cleaned up checkpoint file")

    except Exception as e:
        print(f"❌ Failed to save output: {e}")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
