from datetime import date, datetime, timezone

from app.utils import timezone as tz


def test_dt_br_converts_utc_to_brasilia():
    # 02:30 UTC de 08/10 = 23:30 de 07/10 em Brasília (UTC−3)
    assert tz.dt_br(datetime(2026, 10, 8, 2, 30, tzinfo=timezone.utc)) == "07/10/2026 23:30"
    assert tz.dt_br(datetime(2026, 10, 8, 2, 30, 5), seconds=True) == "07/10/2026 23:30:05"  # naive = UTC (SQLite)
    assert tz.dt_br(datetime(2026, 10, 8, 2, 30), short=True) == "07/10 23:30"
    assert tz.dt_br(None) == "—"


def test_local_today_uses_brasilia_date(monkeypatch):
    class Fake(datetime):
        @classmethod
        def now(cls, tzinfo=None):
            return datetime(2026, 10, 8, 2, 30, tzinfo=timezone.utc).astimezone(tzinfo)

    monkeypatch.setattr(tz, "datetime", Fake)
    assert tz.local_today() == date(2026, 10, 7)


def test_services_share_the_same_today():
    from app.services import chart_service, dashboard_service, due_service, executive_service

    assert due_service.local_today is tz.local_today
    assert chart_service.local_today is tz.local_today
    assert executive_service.local_today is tz.local_today
    assert dashboard_service.local_today is tz.local_today
