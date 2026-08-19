import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.storage.store import Store


class StorageConfigTests(unittest.TestCase):
    def test_postgres_is_preferred_over_rest(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as db:
            store = Store(
                db.name,
                supabase_url="https://example.supabase.co",
                supabase_key="invalid",
                database_url="postgresql://example.invalid/postgres",
            )
            self.assertTrue(store.postgres_configured)
            self.assertEqual(store.backend_name, "postgres_unavailable")

    def test_sqlite_is_not_marked_persistent(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as db:
            store = Store(db.name)
            self.assertFalse(store.persistent_storage_configured)
            self.assertFalse(store.has_persistent_storage)
            self.assertEqual(store.backend_name, "sqlite_ephemeral")


if __name__ == "__main__":
    unittest.main()
