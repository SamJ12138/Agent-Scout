"""The parts of scripts/make_demo_video.py that do not need a browser."""

import shutil
import subprocess

import pytest

import make_demo_video as video


def test_compress_timeline_shortens_only_long_waits_and_reports_them():
    stamps = [0.0, 0.1, 1.6, 1.65, 3.15]
    new, shortened = video.compress_timeline(stamps, max_gap=0.3)
    assert new == [0.0, 0.1, 0.4, 0.45, 0.75]
    assert shortened == [(0.1, pytest.approx(0.4)), (0.45, pytest.approx(0.75))]


def test_compress_timeline_keeps_short_gaps_and_starts_at_zero():
    new, shortened = video.compress_timeline([5.0, 5.1, 5.25], max_gap=0.3)
    assert new == [0.0, 0.1, 0.25] and shortened == []
    assert video.compress_timeline([], 0.3) == ([], [])


def test_wrap_breaks_at_spaces_and_keeps_the_indent():
    line = "      1 of 9 fields stated; unknown: categories, target_user, tasks"
    rows = video.wrap(line, 40)
    assert all(len(row) <= 40 for row in rows)
    assert all(row.startswith("      ") for row in rows)
    assert " ".join(row.strip() for row in rows) == line.strip()
    assert video.wrap("short", 40) == ["short"]
    assert video.wrap("x" * 90, 40) == ["x" * 40, "x" * 40, "x" * 10]


def test_terminal_states_type_the_command_then_replay_every_line_in_order():
    lines = ["first", "second", "third"]
    states = video.terminal_states("run it", lines, [0.0, 2.0, 2.1], fps=30)
    assert states[0].typed == "" and states[0].lines == []
    typed = [state.typed for state in states]
    assert typed == sorted(typed, key=len) and typed[-1] == "run it"
    first_output = next(index for index, state in enumerate(states) if state.lines)
    assert states[first_output].typed == "run it"            # nothing is printed before the command is typed
    counts = [len(state.lines) for state in states]
    assert counts == sorted(counts) and counts[-1] == 3
    assert states[-1].lines == lines
    # the 2-second wait was shortened, and exactly those frames carry the flag
    flagged = [index for index, state in enumerate(states) if state.sped_up]
    assert flagged and all(len(states[index].lines) == 1 for index in flagged)
    assert len(flagged) == pytest.approx(0.3 * 30, abs=1)
    assert not states[-1].sped_up


def test_scroll_positions_are_smooth_monotonic_and_end_exactly():
    positions = video.scroll_positions(100, 700, 1.0, fps=30)
    assert len(positions) == 30 and positions[-1] == 700
    assert positions == sorted(positions) and positions[0] < 110
    steps = [b - a for a, b in zip(positions, positions[1:])]
    assert max(steps) == max(steps[10:20])                    # fastest in the middle
    assert video.scroll_positions(700, 100, 0.5, fps=30)[-1] == 100
    assert video.ease(0) == 0 and video.ease(1) == 1 and video.ease(0.5) == 0.5


def test_every_scene_uses_the_same_encoder_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "ffmpeg_path", lambda: "ffmpeg")
    commands = [video.raw_scene_command(tmp_path / "a.mp4"),
                video.jpeg_scene_command(tmp_path / "b.mp4", tmp_path / "label.png"),
                video.still_scene_command(tmp_path / "s.jpg", 2.0, tmp_path / "c.mp4")]
    for command in commands:
        joined = " ".join(command)
        assert " ".join(video.ENCODER_ARGS) in joined
        assert command[-1].endswith(".mp4")
    assert "-crf 18" in " ".join(video.ENCODER_ARGS) and "yuv420p" in video.ENCODER_ARGS
    assert "libx264" in video.ENCODER_ARGS and "veryfast" in video.ENCODER_ARGS
    assert f"{video.WIDTH}x{video.HEIGHT}" == "1280x720" and video.FPS == 30
    assert "loop=-1:1,trim=duration=2" in " ".join(commands[2])


def test_concat_copies_streams_and_gif_uses_a_two_pass_palette(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "ffmpeg_path", lambda: "ffmpeg")
    command = video.concat_command(tmp_path / "list.txt", tmp_path / "demo.mp4")
    assert command[command.index("-c") + 1] == "copy" and "concat" in command
    listing = video.concat_list([tmp_path / "scene1.mp4", tmp_path / "scene2.mp4"])
    assert listing.count("file '") == 2 and listing.index("scene1") < listing.index("scene2")
    first, second = video.gif_commands(tmp_path / "demo.mp4", tmp_path / "p.png", tmp_path / "demo.gif")
    assert "palettegen" in " ".join(first) and "paletteuse" in " ".join(second)
    assert "fps=10" in " ".join(first) and "scale=960:-1" in " ".join(second)
    assert "max_colors=256" in " ".join(first)
    smaller, _ = video.gif_commands(tmp_path / "demo.mp4", tmp_path / "p.png", tmp_path / "demo.gif", colours=128)
    assert "max_colors=128" in " ".join(smaller) and video.GIF_MAX_BYTES == 8_000_000


def test_labels_say_what_is_shown():
    assert "fictional" in video.SAMPLE_LABEL and "sample" in video.SAMPLE_LABEL
    assert "sped up" in video.SPED_UP_LABEL
    assert video.CLOSING_LINES == ("Every value links to the sentence it came from.",
                                   "What a site does not say stays unknown.")


def test_report_option_requires_its_own_label(tmp_path):
    args = video.build_parser().parse_args(["--report", str(tmp_path / "r.html"), "--label", "Real-site run"])
    assert args.label == "Real-site run"
    with pytest.raises(SystemExit) as stop:
        video.main(["--report", str(tmp_path / "r.html")])
    assert "--label" in str(stop.value)


def test_terminal_frame_is_drawn_at_output_size_with_text_and_label():
    state = video.TerminalState(typed=video.COMMAND, lines=["[1/6] Example (fictional)", "      ok: 6 pages read"],
                                sped_up=True)
    image = video.render_terminal(state)
    assert image.size == (1280, 720)
    colours = {colour for _, colour in image.getcolors(maxcolors=1 << 20)}
    assert video.TERM_BG in colours and len(colours) > 20           # text was drawn
    empty = video.render_terminal(video.TerminalState("", [], False))
    assert image.tobytes() != empty.tobytes()
    strip = image.crop((0, 720 - video.LABEL_HEIGHT, 1280, 720))
    assert video.TERM_BG not in {colour for _, colour in strip.getcolors(maxcolors=1 << 20)}


def test_line_colours_mark_trouble():
    assert video.line_colour("      blocked: HTTP 403 at http://x/") == video.TERM_AMBER
    assert video.line_colour("      ok: 6 pages read") == video.TERM_GREEN
    assert video.line_colour("[1/6] Name   http://x/") == video.TERM_WHITE
    assert video.line_colour("      200   /pricing   0.8 kB  gzip") == video.TERM_FG


def test_closing_card_and_overlay_sizes():
    assert video.render_closing_card().size == (1280, 720)
    overlay = video.label_overlay("Some label")
    assert overlay.size == (1280, 720) and overlay.getpixel((10, 10))[3] == 0
    assert overlay.getpixel((10, 715))[3] == 255


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg is not installed")
def test_still_scene_encodes_to_two_seconds_at_1280x720(tmp_path):
    still = tmp_path / "closing.jpg"
    video.render_closing_card().save(still, quality=95)
    output = tmp_path / "scene3.mp4"
    video.run_to_file(video.still_scene_command(still, 2.0, output), output)
    assert output.is_file() and not (tmp_path / "partial-scene3.mp4").exists()
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,pix_fmt,codec_name,r_frame_rate:format=duration",
                            "-of", "default=nw=1", str(output)], capture_output=True, text=True).stdout
    assert "width=1280" in probe and "height=720" in probe and "pix_fmt=yuv420p" in probe
    assert "codec_name=h264" in probe and "r_frame_rate=30/1" in probe
    assert abs(video.probe_seconds(output) - 2.0) < 0.05


def test_failed_ffmpeg_leaves_no_file(tmp_path):
    output = tmp_path / "out.mp4"
    import sys
    with pytest.raises(SystemExit):
        video.run_to_file([sys.executable, "-c", "import sys; sys.exit(3)", str(output)], output)
    assert not output.exists() and not (tmp_path / "partial-out.mp4").exists()
