from plugin.loader import load_accounts


def test_loads_all_sample_accounts():
    accounts = load_accounts("data/sample_accounts.xlsx")
    assert len(accounts) == 12
    names = {a.name for a in accounts}
    assert "dentsu Canada" in names
    assert "Bell Canada" in names


def test_optional_signal_fields_can_be_none():
    accounts = load_accounts("data/sample_accounts.xlsx")
    bell = next(a for a in accounts if a.name == "Bell Canada")
    assert bell.market_signal_hint is None
    assert bell.rep_notes is None

    dentsu = next(a for a in accounts if a.name == "dentsu Canada")
    assert dentsu.market_signal_hint is not None
