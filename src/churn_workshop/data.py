"""Synthetic data generation and validation (no downloads needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd

CONTRACTS = ["month-to-month", "one-year", "two-year"]

REQUIRED_COLUMNS = {
    "tenure_months": "int",
    "monthly_charges": "float",
    "support_tickets": "int",
    "contract": "str",
    "churned": "int",
}


class DataValidationError(ValueError):
    """Raised when a dataframe does not meet the expected contract."""


def generate_data(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Create a reproducible synthetic customer dataset."""
    rng = np.random.default_rng(seed)
    tenure = rng.integers(1, 72, n)
    monthly = rng.normal(70, 25, n).clip(10, 200).round(2)
    support = rng.poisson(2, n)
    contract = rng.choice(CONTRACTS, n, p=[0.55, 0.25, 0.20])

    logit = (
        -0.04 * tenure
        + 0.02 * monthly
        + 0.35 * support
        + np.where(contract == "month-to-month", 0.9, -0.6)
        - 0.8
    )
    churn_probability = 1 / (1 + np.exp(-logit))
    churned = (rng.random(n) < churn_probability).astype(int)

    return pd.DataFrame(
        {
            "tenure_months": tenure,
            "monthly_charges": monthly,
            "support_tickets": support,
            "contract": contract,
            "churned": churned,
        }
    )


def validate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Check the data contract. Returns df unchanged, or raises DataValidationError."""
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise DataValidationError(f"Missing columns: {sorted(missing)}")

    if df[list(REQUIRED_COLUMNS)].isna().any().any():
        raise DataValidationError("Null values found in required columns")

    if not df["tenure_months"].between(0, 120).all():
        raise DataValidationError("tenure_months must be between 0 and 120")

    if (df["monthly_charges"] <= 0).any():
        raise DataValidationError("monthly_charges must be > 0")

    if (df["support_tickets"] < 0).any():
        raise DataValidationError("support_tickets must be >= 0")

    if not set(df["contract"].unique()) <= set(CONTRACTS):
        raise DataValidationError(f"contract must be one of {CONTRACTS}")

    if not set(df["churned"].unique()) <= {0, 1}:
        raise DataValidationError("churned must be 0 or 1")

    return df
