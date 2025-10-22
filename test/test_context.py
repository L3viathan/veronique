import pytest
import asyncio
from veronique.context import context


@pytest.mark.asyncio
async def test_context_isolated():
    n_set = 0
    event = asyncio.Event()

    async def set_and_check(n):
        nonlocal n_set
        assert context.payload is None

        context.payload = n
        n_set += 1
        if n_set == 2:
            event.set()

        await event.wait()

        assert context.payload == n

    await asyncio.gather(
        set_and_check(1),
        set_and_check(2),
    )
