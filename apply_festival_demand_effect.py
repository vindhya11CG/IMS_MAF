"""
apply_festival_demand_effect.py

WHAT THIS DOES AND WHY IT'S DIFFERENT FROM add_festival_features.py
----------------------------------------------------------------------
add_festival_features.py adds PREDICTOR columns (is_festival_day, etc.).
This script adjusts `daily_demand` ITSELF - the model's actual training
target - by applying a category-aware festival demand uplift.

WHY THIS IS NECESSARY: validate_model_patterns.py showed the model
correctly learning weather patterns but NOT festival patterns. The root
cause, confirmed directly:

    avg_demand_on_festival_days    = 10.75
    avg_demand_on_non_festival_days = 10.66   (a 0.84% difference - noise)

Your synthetic dataset's generator clearly modeled a weather -> demand
relationship (weather_demand_multiplier, weather_adjusted_demand, etc.
already exist as columns, and the trained model's weather-sensitivity
test passes for exactly this reason) but NEVER modeled a festival -> demand
relationship. No feature engineering or model tuning can make a model
learn a pattern that isn't present in the target it's trained against -
this has to be fixed in the data, not the model.

BE HONEST ABOUT WHAT THIS IS: this is a SYNTHETIC augmentation for
demo/validation purposes - it manufactures the effect you want to
demonstrate, using reasonable retail assumptions (see CATEGORY_FESTIVAL_BOOST
below), not a real historical signal. That's a legitimate and standard
thing to do with a synthetic dataset that's missing a relationship you
need to show working end-to-end. It is NOT the same as a production
dataset actually containing organic festival-driven demand history. If
this model or its "learns festival patterns" behavior is ever presented
externally (to a client, in a case study, etc.), say plainly that the
festival effect was synthetically injected into the training data, not
recovered from real sales history - the model's diagnostics can't tell
the difference, but the audience should be able to.

CATEGORY ASSUMPTIONS (edit CATEGORY_FESTIVAL_BOOST to match your retail
judgment - these are defensible retail-industry defaults, not universal
truths):
    Toys, Seasonal        -> highest boost (directly festival-driven categories)
    Electronics, Apparel   -> high boost (major gifting categories)
    Home Goods, Grocery     -> moderate boost (entertaining/hosting driven)
    Health & Beauty         -> modest boost
    Sporting Goods          -> lowest boost (least festival-correlated)

The uplift is applied smoothly via festival_proximity_score (already
computed by add_festival_features.py - 1.0 exactly on a festival day,
decaying over ~7 days either side), not as a hard step function on/off -
this mirrors how the weather effect already ramps continuously with the
underlying weather variables, and is more realistic than a demand spike
that appears and disappears in a single day.

RUN ORDER (each step depends on the columns the previous one adds):
    1. python add_festival_features.py --input <clean.csv> --output <festival.csv>
    2. python apply_festival_demand_effect.py --input <festival.csv> --output <festival_demand.csv>
    3. point data_preparation.py at the file from step 2

Usage:
    python apply_festival_demand_effect.py \
        --input synthetic_inventory_weather_region_v2_festival.csv \
        --output synthetic_inventory_weather_region_v2_festival_demand.csv
"""
import argparse

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["daily_demand", "category_id", "festival_proximity_score", "is_festival_day"]

# category_id -> max festival demand uplift (applied at festival_proximity_score == 1.0,
# i.e. exactly on a festival day; scales down smoothly as proximity decays).
# Mapping from product_categories.csv: 1=Electronics 2=Apparel 3=Home Goods
# 4=Sporting Goods 5=Toys 6=Health & Beauty 7=Grocery 8=Seasonal
CATEGORY_FESTIVAL_BOOST = {
    1: 0.35,   # Electronics - major gifting category
    2: 0.30,   # Apparel - major gifting category
    3: 0.20,   # Home Goods - entertaining/hosting driven
    4: 0.10,   # Sporting Goods - least festival-correlated
    5: 0.50,   # Toys - most directly festival-driven
    6: 0.15,   # Health & Beauty - modest gifting relevance
    7: 0.25,   # Grocery - entertaining/hosting driven
    8: 0.45,   # Seasonal - definitionally festival-driven
}
DEFAULT_BOOST = 0.20  # fallback for any category_id not listed above


def apply_festival_demand_effect(df: pd.DataFrame) -> pd.DataFrame:
    """Pure function - takes a DataFrame with daily_demand, category_id,
    and festival_proximity_score, returns a new DataFrame with
    daily_demand adjusted upward near festivals, scaled by category."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns {missing}. Run add_festival_features.py "
            f"first - this script needs its output."
        )

    df = df.copy()
    boost = df["category_id"].map(CATEGORY_FESTIVAL_BOOST).fillna(DEFAULT_BOOST)
    multiplier = 1.0 + boost * df["festival_proximity_score"]
    df["daily_demand_pre_festival_adjustment"] = df["daily_demand"]
    df["daily_demand"] = (df["daily_demand"] * multiplier).round(6)
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Apply a category-aware festival demand uplift to daily_demand."
    )
    parser.add_argument("--input", default="synthetic_inventory_weather_region_v2_festival.csv")
    parser.add_argument("--output", default="synthetic_inventory_weather_region_v2_festival_demand.csv")
    args = parser.parse_args()

    print(f"[LOAD] Reading {args.input}...")
    df = pd.read_csv(args.input)
    print(f"\u2713 Loaded {len(df):,} rows, {len(df.columns)} columns")

    before_festival = df.loc[df["is_festival_day"] == 1, "daily_demand"].mean()
    before_non = df.loc[df["is_festival_day"] == 0, "daily_demand"].mean()
    print(f"\n[BEFORE] avg demand on festival days:     {before_festival:.3f}")
    print(f"[BEFORE] avg demand on non-festival days: {before_non:.3f}")
    print(f"[BEFORE] difference: {100*(before_festival-before_non)/before_non:+.2f}%")

    print("\n[ADJUST] Applying category-aware festival demand uplift...")
    df = apply_festival_demand_effect(df)

    after_festival = df.loc[df["is_festival_day"] == 1, "daily_demand"].mean()
    after_non = df.loc[df["is_festival_day"] == 0, "daily_demand"].mean()
    print(f"\n[AFTER]  avg demand on festival days:     {after_festival:.3f}")
    print(f"[AFTER]  avg demand on non-festival days: {after_non:.3f}")
    print(f"[AFTER]  difference: {100*(after_festival-after_non)/after_non:+.2f}%")

    print("\n  Per-category effect on festival days (mean daily_demand before -> after):")
    for cat_id in sorted(df["category_id"].unique()):
        mask = (df["category_id"] == cat_id) & (df["is_festival_day"] == 1)
        if mask.sum() == 0:
            continue
        pre = df.loc[mask, "daily_demand_pre_festival_adjustment"].mean()
        post = df.loc[mask, "daily_demand"].mean()
        boost_pct = CATEGORY_FESTIVAL_BOOST.get(cat_id, DEFAULT_BOOST) * 100
        print(f"    category_id={cat_id} (max boost {boost_pct:.0f}%): {pre:.2f} -> {post:.2f}")

    print(f"\n[SAVE] Writing {args.output}...")
    df.to_csv(args.output, index=False)
    print(f"\u2713 {len(df):,} rows written to {args.output}")
    print(f"\n  NOTE: 'daily_demand_pre_festival_adjustment' column preserved for audit/rollback -")
    print(f"  exclude it from training features (it's not in FEATURE_COLS, so this is automatic).")


if __name__ == "__main__":
    main()