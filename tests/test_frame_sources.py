from entok_vision.vision.frame_sources import ADBFrameSource, FFmpegFrameSource, OpenCVFrameSource, ScreenRegionFrameSource, create_frame_source


def test_camera_factory_supports_all_configured_sources():
    assert isinstance(create_frame_source({"source_type": "opencv", "source": 0}), OpenCVFrameSource)
    assert isinstance(create_frame_source({"source_type": "rtsp", "source": "rtsp://example/live"}), OpenCVFrameSource)
    assert isinstance(create_frame_source({"source_type": "ffmpeg", "source": "rtsp://example/live", "frame_width": 640, "frame_height": 360}), FFmpegFrameSource)
    assert isinstance(create_frame_source({"source_type": "screen", "source": "0,0,640,360"}), ScreenRegionFrameSource)
    assert isinstance(create_frame_source({"source_type": "adb", "source": "device"}), ADBFrameSource)
