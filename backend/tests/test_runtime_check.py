import pytest

from app.config.runtime_check import EnvironmentCheckError, check_pyav, check_python


def test_python_too_old_gives_actionable_message():
    with pytest.raises(EnvironmentCheckError, match="3.12"):
        check_python((3, 10, 0))


@pytest.mark.parametrize("version", [(3, 11, 0), (3, 12, 8), (3, 13, 1)])
def test_supported_python_passes(version):
    check_python(version)


@pytest.mark.parametrize("version", ["15.1.0", "17.0.0", "18.1.1"])
def test_compatible_pyav_passes(version):
    check_pyav(version)


@pytest.mark.parametrize("version", ["19.0.2", "20.0.0", "12.3.0"])
def test_incompatible_pyav_is_rejected(version):
    with pytest.raises(EnvironmentCheckError, match="metadata_errors"):
        check_pyav(version)
