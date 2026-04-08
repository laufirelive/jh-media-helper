from src.worker.ffmpeg_worker import parse_progress


class TestParseProgress:
    def test_parse_frame_number(self):
        line = "frame=  810 fps=120 q=28.0 size=   25600kB time=00:00:06.75"
        assert parse_progress(line) == 810

    def test_parse_frame_no_spaces(self):
        line = "frame=1247 fps=95.2 q=31.0 Lsize=  102400kB time=00:00:10.39"
        assert parse_progress(line) == 1247

    def test_no_frame_returns_none(self):
        line = "Press [q] to stop, [?] for help"
        assert parse_progress(line) is None

    def test_empty_line(self):
        assert parse_progress("") is None
