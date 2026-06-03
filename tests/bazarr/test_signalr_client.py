from app import signalr_client


class _FakeState:
    def __init__(self, value):
        self.value = value


class _FakeTransport:
    def __init__(self, value):
        self.state = _FakeState(value)


class _FakeConnection:
    def __init__(self):
        self.transport = None
        self.starts = 0

    def start(self):
        self.starts += 1
        self.transport = _FakeTransport(1)
        return True


def test_sonarr_signalr_start_handles_missing_transport_before_first_start(monkeypatch):
    connection = _FakeConnection()
    client = signalr_client.SonarrSignalrClient()

    monkeypatch.setattr(signalr_client.get_sonarr_info, "version", lambda: "4.0.0")
    monkeypatch.setattr(signalr_client.get_sonarr_info, "supports_signalr_core", lambda: True)
    monkeypatch.setattr(client, "configure", lambda: setattr(client, "connection", connection))

    client.start()

    assert connection.starts == 1


def test_sonarr_signalr_start_waits_when_version_is_temporarily_unknown(monkeypatch):
    connection = _FakeConnection()
    client = signalr_client.SonarrSignalrClient()
    versions = iter(["unknown", "4.0.0"])
    sleep_calls = []

    monkeypatch.setattr(signalr_client.get_sonarr_info, "version", lambda: next(versions))
    monkeypatch.setattr(signalr_client.get_sonarr_info, "supports_signalr_core", lambda: True)
    monkeypatch.setattr(signalr_client.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(client, "configure", lambda: setattr(client, "connection", connection))

    client.start()

    assert sleep_calls == [5]
    assert connection.starts == 1


def test_sonarr_signalr_start_disables_known_unsupported_version(monkeypatch):
    client = signalr_client.SonarrSignalrClient()
    events = []

    monkeypatch.setattr(signalr_client.get_sonarr_info, "version", lambda: "3.0.0")
    monkeypatch.setattr(signalr_client.get_sonarr_info, "supports_signalr_core", lambda: False)
    monkeypatch.setattr(signalr_client, "event_stream", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr(client, "configure", lambda: (_ for _ in ()).throw(AssertionError("configure called")))

    client.start()

    assert client.connected is False
    assert events == [{"type": "badges"}]


def test_radarr_signalr_start_handles_missing_transport_before_first_start(monkeypatch):
    connection = _FakeConnection()
    client = signalr_client.RadarrSignalrClient()

    monkeypatch.setattr(client, "configure", lambda: setattr(client, "connection", connection))

    client.start()

    assert connection.starts == 1


def test_sonarr_on_reconnect_handler_sets_connected_true(monkeypatch):
    # Why: signalrcore's handle_reconnect fires on_reconnect (this handler) but
    # NOT on_open after an auto-reconnect, so on_connect_handler never runs and
    # the flag would otherwise stay False permanently while the socket is live.
    # Test: after on_reconnect_handler, connected must be True and a badges event
    # must be emitted.
    client = signalr_client.SonarrSignalrClient()
    client.connected = False
    events = []
    monkeypatch.setattr(signalr_client, "event_stream", lambda **kwargs: events.append(kwargs))

    client.on_reconnect_handler()

    assert client.connected is True
    assert events == [{"type": "badges"}]


def test_radarr_on_reconnect_handler_sets_connected_true(monkeypatch):
    # Why/Test: mirror of the Sonarr reconnect handler regression guard; the
    # library never re-fires on_open after auto-reconnect so this handler is the
    # only place that can restore connected=True for Radarr.
    client = signalr_client.RadarrSignalrClient()
    client.connected = False
    events = []
    monkeypatch.setattr(signalr_client, "event_stream", lambda **kwargs: events.append(kwargs))

    client.on_reconnect_handler()

    assert client.connected is True
    assert events == [{"type": "badges"}]
