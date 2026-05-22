from system.scripts import healthcheck


def test_healthcheck_module_imports() -> None:
    assert callable(healthcheck.main)
