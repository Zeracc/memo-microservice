import unittest
from unittest.mock import patch

from app.core import database


class DatabaseEngineConfigTests(unittest.TestCase):
    def test_build_engine_kwargs_disables_statement_cache_for_supabase_pooler(self) -> None:
        database_url = (
            "postgresql+asyncpg://postgres.project-ref:secret@"
            "aws-1-us-east-2.pooler.supabase.com:6543/postgres?ssl=require"
        )

        with patch.object(database.settings, "database_disable_prepared_statements", None):
            kwargs = database._build_engine_kwargs(database_url)

        self.assertEqual(kwargs["pool_pre_ping"], True)
        self.assertEqual(
            kwargs["connect_args"],
            {
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        )

    def test_build_engine_kwargs_keeps_default_behavior_for_regular_postgres(self) -> None:
        database_url = "postgresql+asyncpg://postgres:postgres@postgres:5432/memo"

        with patch.object(database.settings, "database_disable_prepared_statements", None):
            kwargs = database._build_engine_kwargs(database_url)

        self.assertEqual(kwargs, {"pool_pre_ping": True})

    def test_explicit_setting_overrides_auto_detection(self) -> None:
        database_url = "postgresql+asyncpg://postgres:postgres@postgres:5432/memo"

        with patch.object(database.settings, "database_disable_prepared_statements", True):
            kwargs = database._build_engine_kwargs(database_url)

        self.assertEqual(
            kwargs,
            {
                "pool_pre_ping": True,
                "connect_args": {
                    "statement_cache_size": 0,
                    "prepared_statement_cache_size": 0,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
