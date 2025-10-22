import pytest

import veronique.objects as O
from veronique import db
from veronique.context import context


# Not super happy with this yet — I would prefer to make real requests.


@pytest.mark.usefixtures("conn")
def test_fresh_db():
    assert {v.id for v in O.Verb.all()} == set(db.DATA_LABELS)
    assert {c.id for c in O.Claim.all()} == set()
    assert {q.id for q in O.Query.all()} == set()
    assert {u.id for u in O.User.all()} == {0}


@pytest.mark.usefixtures("conn")
def test_new_user_cant_do_shit(regular_user):
    assert not regular_user.can("write", "verb", -1)


@pytest.mark.usefixtures("conn")
def test_admin_can_do_whatever():
    assert context.user.can("write", "verb", -1)
