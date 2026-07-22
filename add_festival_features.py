"""
add_festival_features.py

Standalone, one-off enrichment script - NOT part of the training_models
package, not imported by anything at training time. Run it once (or
whenever you regenerate the synthetic dataset) to bake 5 festival/holiday
columns directly into the CSV, the same way weather/region columns
already sit as plain static columns in
synthetic_inventory_weather_region_v2_clean.csv. After this runs,
data_preparation.py needs zero special-case code for festivals - the
columns are just... there, like every other column.

WHY A LIBRARY INSTEAD OF HAND-TYPED DATES: several of the most
demand-relevant festivals (Diwali, Holi, Eid, Easter) are movable feasts
computed from lunar/lunisolar calendars - dates shift every year and are
easy to get subtly wrong by hand, especially for future years. This uses
the `holidays` PyPI package as the source of truth per country
(keyed off your existing country_code column), plus a small custom
overlay for retail "shopping season" windows that aren't public holidays
but move demand (Black Friday, Diwali shopping week, Midsummer week).

KNOWN LIBRARY QUIRK, HANDLED HERE: Sweden's raw holiday data flags EVERY
Sunday as a holiday. Verified: 63 flagged days/year -> 13 real ones after
filtering. Left unfiltered, is_festival_day would be indistinguishable
from day-of-week for Sweden and would wreck days_to_next_festival /
festival_proximity_score. _clean() strips pure "every Sunday" entries
while keeping compound ones like "Påskdagen; Söndag" (a real holiday that
happens to fall on a Sunday).

IMPORTANT: the `holidays` package's default language for a given country
can differ across versions/environments (observed: Swedish "Söndag" in
one environment, English "Sunday" in another, for the same country code).
_clean() checks BOTH translations, case-insensitively, so the filter
doesn't silently stop working just because pip resolved a different
package version on a different machine. main() also prints a self-check
(raw vs. cleaned count for Sweden) so a filter regression like this is
visible in the terminal immediately instead of only showing up later as
an unexplained validate_model_patterns.py failure.
"""
import argparse
from functools import lru_cache

import numpy as np
import pandas as pd

try:
    import holidays as holidays_lib
except ImportError:
    raise SystemExit(
        "This script requires the `holidays` package.\n  pip install holidays"
    )

# Countries confirmed in the dataset today. Add ISO-3166 alpha-2 codes here
# as new regions are onboarded - nothing else in this script changes.
SUPPORTED_COUNTRY_CODES = ["US", "IN", "SE"]

# Names that mean "just a Sunday, not a real holiday" - checked in both
# languages since the `holidays` package's default language for a country
# isn't guaranteed identical across versions/environments.
_PURE_WEEKDAY_FLAG_NAMES = {"söndag", "sunday"}

# Coarse retail "shopping season" windows - NOT public holidays, but
# demand-moving. (month, day_start, day_end), applies every year.
_SHOPPING_SEASON_WINDOWS = {
    "US": [(11, 20, 30), (12, 1, 26)],   # Black Friday/Cyber Monday -> Christmas
    "IN": [(10, 1, 31), (11, 1, 15)],    # Navratri/Dussehra -> Diwali shopping season
    "SE": [(6, 15, 26), (12, 1, 24)],    # Midsummer week, Christmas run-up
}

FESTIVAL_COLUMNS = [
    "is_festival_day",
    "days_to_next_festival",
    "days_since_last_festival",
    "festival_proximity_score",
    "is_shopping_season",
]

LOOKAHEAD_CAP = 30  # cap days_to/since at 30 for numerical stability


def _clean(raw: dict) -> dict:
    return {d: name for d, name in raw.items() if name.strip().lower() not in _PURE_WEEKDAY_FLAG_NAMES}


def _self_check_sweden():
    """Prints raw-vs-cleaned holiday counts for Sweden so a filter
    regression (e.g. a library version returning names in a language
    _clean() doesn't recognize) is visible immediately, not discovered
    later via a failing validation check."""
    if "SE" not in SUPPORTED_COUNTRY_CODES:
        return
    try:
        raw = holidays_lib.country_holidays("SE", years=[2025])
        cleaned = _clean(dict(raw))
        raw_rate = 100 * len(raw) / 365
        clean_rate = 100 * len(cleaned) / 365
        print(f"[SELF-CHECK] Sweden 2025: {len(raw)} raw holiday entries ({raw_rate:.1f}% of days) "
              f"-> {len(cleaned)} after filtering ({clean_rate:.1f}% of days)")
        if clean_rate > 6.0:
            print(f"  WARNING: {clean_rate:.1f}% still looks too high for real Swedish public "
                  f"holidays (~3.5%/year expected). The Sunday-name filter may not be matching "
                  f"names from your installed `holidays` package version - inspect "
                  f"`holidays.country_holidays('SE', years=[2025])` directly and add whatever "
                  f"name it uses to _PURE_WEEKDAY_FLAG_NAMES above.")
    except Exception as e:
        print(f"[SELF-CHECK] Could not verify Sweden filtering: {e}")


@lru_cache(maxsize=None)
def _country_holiday_dates(country_code: str, year: int) -> frozenset:
    if country_code not in SUPPORTED_COUNTRY_CODES:
        return frozenset()
    try:
        raw = holidays_lib.country_holidays(country_code, years=[year - 1, year, year + 1])
        return frozenset(_clean(dict(raw)).keys())
    except Exception:
        return frozenset()


def _nearest_distance(date, country_code):
    dates = _country_holiday_dates(country_code, date.year)
    if not dates:
        return float(LOOKAHEAD_CAP), float(LOOKAHEAD_CAP)
    future = [(d - date).days for d in dates if d >= date]
    past = [(date - d).days for d in dates if d <= date]
    days_to_next = min(future) if future else LOOKAHEAD_CAP
    days_since_last = min(past) if past else LOOKAHEAD_CAP
    return float(min(days_to_next, LOOKAHEAD_CAP)), float(min(days_since_last, LOOKAHEAD_CAP))


def _is_shopping_season(date, country_code):
    for month, day_start, day_end in _SHOPPING_SEASON_WINDOWS.get(country_code, []):
        if date.month == month and day_start <= date.day <= day_end:
            return 1
    return 0


def add_festival_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pure function - takes a DataFrame with 'date' + 'country_code',
    returns a new DataFrame with the 5 FESTIVAL_COLUMNS added. Importable
    for testing; main() below is the CLI wrapper around it."""
    if "date" not in df.columns or "country_code" not in df.columns:
        raise ValueError("CSV must have 'date' and 'country_code' columns.")

    dates = pd.to_datetime(df["date"], errors="coerce").dt.date
    codes = df["country_code"].astype(str)

    n = len(df)
    is_festival_day = np.zeros(n, dtype=int)
    days_to_next = np.full(n, float(LOOKAHEAD_CAP))
    days_since_last = np.full(n, float(LOOKAHEAD_CAP))
    is_shopping = np.zeros(n, dtype=int)

    for i, (d, code) in enumerate(zip(dates, codes)):
        if d is None or pd.isna(d):
            continue
        holiday_dates = _country_holiday_dates(code, d.year)
        is_festival_day[i] = int(d in holiday_dates)
        dn, ds = _nearest_distance(d, code)
        days_to_next[i] = dn
        days_since_last[i] = ds
        is_shopping[i] = _is_shopping_season(d, code)

    df = df.copy()
    df["is_festival_day"] = is_festival_day
    df["days_to_next_festival"] = days_to_next
    df["days_since_last_festival"] = days_since_last
    df["festival_proximity_score"] = np.exp(-np.minimum(days_to_next, days_since_last) / 7.0)
    df["is_shopping_season"] = is_shopping
    return df


def main():
    parser = argparse.ArgumentParser(description="Bake festival/holiday features into the training CSV.")
    parser.add_argument("--input", default="synthetic_inventory_weather_region_v2_clean.csv")
    parser.add_argument("--output", default="synthetic_inventory_weather_region_v2_festival.csv")
    args = parser.parse_args()

    _self_check_sweden()
    print()

    print(f"[LOAD] Reading {args.input}...")
    df = pd.read_csv(args.input)
    print(f"\u2713 Loaded {len(df):,} rows, {len(df.columns)} columns")

    print("[ENRICH] Computing festival/holiday features...")
    df = add_festival_features(df)
    print(f"\u2713 Added columns: {FESTIVAL_COLUMNS}")

    if "country_code" in df.columns:
        print("\n  Festival-day coverage by country:")
        summary = df.groupby("country_code")["is_festival_day"].agg(["sum", "count"])
        for code, row in summary.iterrows():
            pct = 100 * row["sum"] / row["count"] if row["count"] else 0
            print(f"    {code}: {int(row['sum'])} festival rows / {int(row['count'])} total ({pct:.2f}%)")

    print(f"\n[SAVE] Writing {args.output}...")
    df.to_csv(args.output, index=False)
    print(f"\u2713 {len(df):,} rows written to {args.output}")


if __name__ == "__main__":
    main()