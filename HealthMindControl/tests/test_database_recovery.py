from types import SimpleNamespace

from healthmind_control.db.database import Database


def test_network_failure_temporarily_disables_schema_compatible_writes_then_recovers():
    db = Database(SimpleNamespace())
    db.pool = object()
    db._schema_compatible = True
    db._write_features = {
        "recovery": True, "releases": True, "debug": True, "expert": True, "fixtures": True,
    }
    db.connected = True

    db._mark_down("temporary outage")
    assert db.write_enabled is False
    assert not any(db.write_features.values())
    assert "temporary outage" in (db.schema_error or "")

    # verify_schema calls _mark_up only after all compatibility queries succeed.
    db._mark_up()
    assert db.write_enabled is True
    assert all(db.write_features.values())
    assert db.schema_error is None


def test_schema_incompatibility_remains_disabled_after_network_recovers():
    db = Database(SimpleNamespace())
    db.pool = object()
    db._schema_compatible = False
    db._schema_error = "缺少数据表"
    db._write_features = {name: False for name in db._write_features}
    db._mark_up()

    assert db.connected is True
    assert db.write_enabled is False
    assert db.schema_error == "缺少数据表"
