from types import SimpleNamespace

from ai.vigi_ptz import PTZSettings, VigiPTZ, settings_from_source


class FakePTZService:
    def __init__(self):
        self.moves = []
        self.stop_calls = 0

    def create_type(self, name):
        return SimpleNamespace(type_name=name)

    def GetStatus(self, _request):
        return SimpleNamespace(
            Position=SimpleNamespace(
                PanTilt=SimpleNamespace(x=0.0, y=0.0),
                Zoom=SimpleNamespace(x=0.0),
            )
        )

    def ContinuousMove(self, request):
        self.moves.append(
            (request.Velocity.PanTilt.x, request.Velocity.PanTilt.y)
        )

    def Stop(self, _request):
        self.stop_calls += 1


def connected_controller(speed=0.35):
    controller = VigiPTZ(
        PTZSettings(
            host="192.0.2.10",
            ports=(2020,),
            username="admin",
            password="secret",
            speed=speed,
            hold_timeout_seconds=2.0,
        )
    )
    service = FakePTZService()
    controller._ptz = service
    controller._profile_token = "profile-1"
    controller.connected_port = 2020
    return controller, service


def test_settings_prioritize_active_rtsp_credentials_over_legacy_cctv_values():
    settings = settings_from_source(
        "rtsp://fallback:encoded%21@example.invalid:554/stream1",
        {
            "onvif_port": 2020,
            "onvif_fallback_ports": [80],
            "ptz_speed": 0.4,
        },
        {
            "CCTV_HOST": "192.0.2.20",
            "CCTV_USERNAME": "camera-user",
            "CCTV_PASSWORD": "camera-pass",
        },
    )

    assert settings.host == "192.0.2.20"
    assert settings.ports == (2020, 80)
    assert settings.username == "fallback"
    assert settings.password == "encoded!"
    assert settings.speed == 0.4


def test_held_direction_does_not_spam_continuous_move_and_release_stops():
    controller, service = connected_controller(speed=0.35)
    try:
        assert controller.start_move("left") is True
        assert controller.start_move("left") is True
        assert service.moves == [(-0.35, 0.0)]

        assert controller.start_move("up") is True
        assert service.moves[-1] == (0.0, 0.35)
        assert len(service.moves) == 2

        assert controller.stop() is True
        assert service.stop_calls == 1
        assert controller.current_direction is None
    finally:
        controller.close()
