from types import SimpleNamespace

import pytest

from veronique.data_types import TYPES
from veronique.db import VALID_FROM, VALID_UNTIL
from veronique.objects import Claim, Plain


def date_prop(id_=0):
    return SimpleNamespace(id=id_, data_type=TYPES["date"])


def test_unknown_regular_date_is_still_allowed():
    assert Plain.from_form(date_prop(), {"value": "????"}).value == "????-??-??"


@pytest.mark.parametrize("verb_id", [VALID_FROM, VALID_UNTIL])
def test_unknown_validity_boundary_is_allowed_in_form(verb_id):
    assert Plain.from_form(date_prop(verb_id), {"value": "????"}).value == "????-??-??"


def claim_value(value):
    return [SimpleNamespace(object=SimpleNamespace(value=value))]


def test_unknown_valid_from_makes_claim_invalid():
    assert Claim(1)._get_invalid({VALID_FROM: claim_value("????-??-??")}) == (
        "????-??-??",
        None,
    )


def test_unknown_valid_until_makes_claim_invalid():
    assert Claim(1)._get_invalid({VALID_UNTIL: claim_value("????-??-??")}) == (
        None,
        "????-??-??",
    )
