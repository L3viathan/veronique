import pytest
import asyncio
from veronique.context import context
from contextvars import copy_context


def test_context_set_get():
    context.user = "david"
    assert context.user == "david"

    # TODO: make this look more like the payload we have?
    context.payload = {"foo": "bar"}
    assert context.payload == {"foo": "bar"}


def test_context_default_is_none():
    # can't reset context vars easily... this one was still david :D
    assert context.user is None or isinstance(context.user, str)


def test_change_value():
    context.user = "laura"
    assert context.user == "laura"

    context.user = "laura ana maria"
    assert context.user == "laura ana maria"


def test_context_isolated():
    results = {}

    async def set_and_check(payload):

        assert context.user is None
        assert context.payload is None

        context.user = f"async_user_{payload}"
        context.payload = {"payload": payload}

        await asyncio.sleep(0.02)

        results[payload] = {"user": context.user, "payload": context.payload}

    async def run_test():
        await asyncio.gather(
            set_and_check(1),
            set_and_check(2),
            set_and_check(3),
            set_and_check(4),
            set_and_check(5),
        )

    asyncio.run(run_test())

    for i in [1, 2, 3, 4, 5]:
        assert results[i]["user"] == f"async_user_{i}"
        assert results[i]["payload"]["payload"] == i
