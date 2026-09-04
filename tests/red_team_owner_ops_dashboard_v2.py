from owner_ops.local_ui import DASHBOARD_HTML

def test_dashboard_red_team_properties():
    low = DASHBOARD_HTML.lower()
    assert "innerhtml" not in low
    assert "eval(" not in low
    assert "document.write" not in low
    assert "https://" not in low
    assert "http://" not in low
    assert "setinterval(refresh,1000)" not in low
    assert "setinterval(refresh,60000)" in low
    assert 'fetch("/api/status"' in low
    assert "<iframe" not in low
    assert "<img" not in low
