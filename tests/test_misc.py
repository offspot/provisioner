import datetime as dt

import humanfriendly

from provisioner.utils.misc import (
    format_dt,
    format_duration,
    format_size,
    format_speed,
    get_environ,
    get_estimated_duration,
    get_now,
    yesno,
)


def test_format_size():
    assert format_size(5000000) == "5 MB"


def test_format_duration():
    assert format_duration(1) == "1 second"


def test_format_speed():
    assert format_speed(1, 1) == "1 byte/s"


def test_yesno():
    assert yesno(True) == "yes"
    assert yesno(False) == "no"


def test_format_dt():
    adt = dt.datetime(2025, 1, 1, 0, 0)  # noqa: DTZ001
    assert (
        format_dt(adt, fmt="long", locale="en") == "January 1, 2025, 12:00:00 AM UTC"  # noqa: RUF001
    )


def test_get_estimated_duration():
    assert get_estimated_duration(1) == 120
    assert get_estimated_duration(humanfriendly.parse_size("100GB")) == 600


def test_get_now():
    adt = get_now()
    assert isinstance(adt, dt.datetime)
    assert adt.tzinfo == dt.UTC


def test_get_environ():
    env = get_environ()
    assert isinstance(env, dict)
    for key in ("LANG", "LANGUAGE", "LC_ALL"):
        assert key in env
        assert "UTF-8" in env[key]
