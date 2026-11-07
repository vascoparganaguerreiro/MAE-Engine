"""data_store tests with a fake Supabase client and a fake `st` (no network, no running Streamlit)."""
from datetime import date

import data_store as store


class FakeSt:
    def __init__(self, user=None):
        self.session_state = {"user": user} if user else {}
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


class User:
    id = "uid-1"
    access_token = "TOKEN-1"


class FakeQuery:
    def __init__(self, client):
        self.client = client

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self

    def upsert(self, payload, on_conflict=None):
        self.client.upserts.append((payload, on_conflict))
        return self

    def execute(self):
        if self.client.fail:
            raise RuntimeError("permission denied for table daily_telemetry")
        class Result: data = self.client.rows
        return Result()


class FakeClient:
    def __init__(self, fail=False, rows=None):
        self.fail, self.rows, self.upserts, self.tokens = fail, rows or [], [], []
        self.postgrest = self

    def auth(self, token): self.tokens.append(token)
    def table(self, name): return FakeQuery(self)


def use(monkeypatch, user=None, client=None):
    fake_st = FakeSt(user)
    monkeypatch.setattr(store, "st", fake_st)
    if client is not None:
        monkeypatch.setattr(store, "_get_supabase", lambda: client)
    return fake_st


def test_history_is_grouped_so_nulls_never_overwrite_existing_values(monkeypatch):
    client = FakeClient()
    use(monkeypatch, User(), client)
    written = store.bulk_insert_garmin_history([
        {"date": "2026-11-01", "hrv": 60.0},
        {"date": "2026-11-02", "hrv": 61.0, "rhr": 50.0},
        {"date": "2026-11-03", "rhr": 49.0},
        {"date": "2026-11-04"},                       # nothing measured: skipped, not written as zeros
    ])
    assert written == 3
    rows = [r for payload, _ in client.upserts for r in payload]
    assert all(v is not None for r in rows for v in r.values())
    assert {tuple(sorted(r)) for r in rows} == {("date", "hrv", "source", "user_id"),
                                                 ("date", "hrv", "rhr", "source", "user_id"),
                                                 ("date", "rhr", "source", "user_id")}
    assert all(on_conflict == "user_id,date" for _, on_conflict in client.upserts)


def test_nothing_is_written_without_a_logged_in_user(monkeypatch):
    client = FakeClient()
    use(monkeypatch, None, client)
    assert store.bulk_insert_garmin_history([{"date": "2026-11-01", "hrv": 60}]) == 0
    assert store.upsert_daily_metrics(date(2026, 11, 1), {"hrv": 60}) is False
    assert store.fetch_daily_metrics(date(2026, 10, 1), date(2026, 11, 1)).empty
    assert client.upserts == []


def test_upsert_skips_missing_values(monkeypatch):
    client = FakeClient()
    use(monkeypatch, User(), client)
    assert store.upsert_daily_metrics(date(2026, 11, 1), {"hrv": 60.0, "rhr": None, "sleep_score": float("nan")}) is True
    payload, _ = client.upserts[0]
    assert payload == {"user_id": "uid-1", "date": "2026-11-01", "source": "garmin", "hrv": 60.0}


def test_database_errors_are_shown_once_not_swallowed(monkeypatch):
    fake_st = use(monkeypatch, User(), FakeClient(fail=True))
    for _ in range(3):
        assert store.fetch_daily_metrics(date(2026, 10, 1), date(2026, 11, 1)).empty
    assert len(fake_st.warnings) == 1 and "permission denied" in fake_st.warnings[0]


def test_each_session_gets_its_own_client_with_its_own_token(monkeypatch):
    made = []

    def fake_create(url, key):
        client = FakeClient()
        made.append(client)
        return client

    monkeypatch.setattr(store, "create_client", fake_create)
    monkeypatch.setattr(store, "st", FakeSt(User()))
    first = store._get_supabase()
    assert store._get_supabase() is first and first.tokens == ["TOKEN-1"]     # reused inside a session

    other_user = User()
    other_user.access_token = "TOKEN-2"
    monkeypatch.setattr(store, "st", FakeSt(other_user))                       # a different visitor
    second = store._get_supabase()
    assert second is not first and second.tokens == ["TOKEN-2"]

    store.st.session_state["user"].access_token = "TOKEN-3"                    # token refreshed
    assert store._get_supabase().tokens == ["TOKEN-3"]


def test_settings_use_the_session_and_both_names_exist(monkeypatch):
    use(monkeypatch)
    store.set_setting("mode", "longevity")
    assert store.get_setting("mode") == "longevity"
    store.save_setting("language", "PT")
    assert store.get_setting("language") == "PT" and store.get_setting("missing", 7) == 7
