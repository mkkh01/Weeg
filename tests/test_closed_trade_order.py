import asyncio
import unittest
from unittest.mock import AsyncMock

from app.storage.store import Store


class ClosedTradeOrderTests(unittest.TestCase):
    def test_closed_trades_are_ordered_by_closed_at(self):
        async def run():
            store = Store(":memory:", database_url="postgresql://example.invalid/weeg")
            store.persistent_storage_ready = True
            store.storage_key_source = "postgres"
            store._pg_query = AsyncMock(return_value=[])
            await store.list_trades("CLOSED_OR_STOPPED")
            query = store._pg_query.await_args.args[0]
            self.assertIn("order by closed_at desc nulls last", query)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
