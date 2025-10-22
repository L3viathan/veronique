import pytest
import asyncio
from veronique.context import context
from contextvars import copy_context


@pytest.mark.asyncio
async def test_context_isolated():
    async def set_and_check(n, barrier):
        assert context.payload is None

        context.payload = n

        await barrier.wait()

        assert context.payload == n

    barrier = asyncio.Barrier(2)
    await asyncio.gather(
        set_and_check(1, barrier),
        set_and_check(2, barrier),
    )
