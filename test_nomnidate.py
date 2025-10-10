from datetime import date

import pytest

from nomnidate import *

REFERENCE_DATE = date(2024, 10, 9)


@pytest.mark.parametrize(
    ("datestring", "difference"),
    [
        ("2024-10-09", NonOmniscientDatedelta(years=0, days=0)),
        ("2024-10-12", NonOmniscientDatedelta(years=0, days=-3)),
        ("2024-10-05", NonOmniscientDatedelta(years=0, days=4)),
        ("2025-10-05", NonOmniscientDatedelta(years=-1, days=4)),
        ("2023-10-12", NonOmniscientDatedelta(years=1, days=-3)),
        ("2023-10-01", NonOmniscientDatedelta(years=1, days=8)),
        ("????-10-01", NonOmniscientDatedelta(years=None, days=8)),
        ("2023-??-??", NonOmniscientDatedelta(years=1, days=None)),
        ("2023-12-??", NonOmniscientDatedelta(years=1, days=None)),
        ("20??-12-??", NonOmniscientDatedelta(years=None, days=None)),
    ],
)
def test_nomnidate_delta(datestring, difference):
    nomnidate = NonOmniscientDate(datestring)
    assert REFERENCE_DATE - nomnidate == difference


@pytest.mark.parametrize(
    ("delta", "output"),
    [
        (NonOmniscientDatedelta(years=0, days=0), "today"),
        (NonOmniscientDatedelta(years=0, days=1), "yesterday"),
        (NonOmniscientDatedelta(years=0, days=-1), "tomorrow"),
        (NonOmniscientDatedelta(years=0, days=-5), "in 5 days"),
        (NonOmniscientDatedelta(years=0, days=5), "5 days ago"),
        (NonOmniscientDatedelta(years=1, days=1), "last year, yesterday"),
        (NonOmniscientDatedelta(years=3, days=5), "3 years and 5 days ago"),
        (NonOmniscientDatedelta(years=-1, days=-1), "next year, tomorrow"),
        (NonOmniscientDatedelta(years=-3, days=-4), "in 3 years and 4 days"),
        (NonOmniscientDatedelta(years=1, days=0), "last year, today"),
        (NonOmniscientDatedelta(years=-1, days=0), "1 year from today"),
        (NonOmniscientDatedelta(years=-3, days=0), "3 years from today"),
        (NonOmniscientDatedelta(years=-3, days=3), "in 3 years, 3 days ago"),
        (NonOmniscientDatedelta(years=-1, days=1), "next year, yesterday"),
        (NonOmniscientDatedelta(years=1, days=-1), "tomorrow, last year"),
        (NonOmniscientDatedelta(years=None, days=-1), "some year, tomorrow"),
        (NonOmniscientDatedelta(years=None, days=5), "some year, 5 days ago"),
        (NonOmniscientDatedelta(years=None, days=0), "some year, today"),
        (NonOmniscientDatedelta(years=1, days=None), "some day last year"),
        (NonOmniscientDatedelta(years=-1, days=None), "some day next year"),
        (NonOmniscientDatedelta(years=-3, days=None), "some day in 3 years"),
        (NonOmniscientDatedelta(years=0, days=None), "some day this year"),
        (NonOmniscientDatedelta(years=None, days=None), "some day"),
    ],
)
def test_datedelta_str(delta, output):
    assert str(delta) == output
