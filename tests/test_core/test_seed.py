from types import SimpleNamespace

from backend.core import mysql_client, seed
from backend.repositories import user as user_repository


class _FakeSession:
    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def _record_seeded_usernames(monkeypatch) -> list[str]:
    seeded: list[str] = []
    monkeypatch.setattr(mysql_client, "SessionLocal", _FakeSession)
    monkeypatch.setattr(user_repository, "ensure_seed_user", lambda db, **account: seeded.append(account["username"]))
    return seeded


def test_seed_users_never_creates_public_test_accounts_in_production(monkeypatch):
    seeded = _record_seeded_usernames(monkeypatch)
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(is_production=True))

    seed.seed_users()

    assert seeded == []


def test_seed_users_creates_test_accounts_in_development(monkeypatch):
    seeded = _record_seeded_usernames(monkeypatch)
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(is_production=False))

    seed.seed_users()

    assert seeded == [account["username"] for account in seed.SEED_USERS]
