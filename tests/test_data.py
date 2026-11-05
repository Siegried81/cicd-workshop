import pytest

from churn_workshop.data import DataValidationError, generate_data, validate_data


def test_generate_data_is_reproducible():
    assert generate_data(100, seed=1).equals(generate_data(100, seed=1))


def test_generated_data_is_valid():
    validate_data(generate_data(200))


def test_missing_column_is_rejected():
    df = generate_data(50).drop(columns=["contract"])
    with pytest.raises(DataValidationError, match="Missing columns"):
        validate_data(df)


def test_nulls_are_rejected():
    df = generate_data(50)
    df.loc[0, "monthly_charges"] = None
    with pytest.raises(DataValidationError, match="Null"):
        validate_data(df)


def test_negative_charges_are_rejected():
    df = generate_data(50)
    df.loc[0, "monthly_charges"] = -5
    with pytest.raises(DataValidationError, match="monthly_charges"):
        validate_data(df)


def test_negative_support_tickets_are_rejected():
    df = generate_data(50)
    df.loc[0, "support_tickets"] = -1
    with pytest.raises(DataValidationError, match="support_tickets"):
        validate_data(df)


def test_unknown_contract_is_rejected():
    df = generate_data(50)
    df.loc[0, "contract"] = "lifetime"
    with pytest.raises(DataValidationError, match="contract"):
        validate_data(df)
