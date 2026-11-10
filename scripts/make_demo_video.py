"""Render the demo video: docs/demo.mp4 and docs/demo.gif.

    python scripts/make_demo_video.py

Nothing is recorded by hand. The script

1. serves the bundled fictional sample sites on 127.0.0.1, runs
   `agent-scout run` on them with the default settings and records every
   console line with the moment it appeared;
2. scene 1: draws a terminal with Pillow: the command being typed, then the
   recorded lines. Waits longer than 0.3 s (the pauses the tool leaves between
   requests) are shortened, and a label says so while that happens;
3. scene 2: films the report.html of that run in headless Chromium: the
   comparison table (scrolled so that its last row is clear of the caption),
   one profile opened, one value with its quote and source link, then the
   rows of the sites that could not be read;
4. scene 3: a two-second closing card;
5. encodes each scene to its own .mp4 with identical settings, joins them
   with the concat demuxer, and makes a 960 px GIF with a two-pass palette.

Scenes 1 and 2 carry an on-screen label saying the data is bundled fictional
sample sites. To film a different report in scene 2 (for example the
real-corpus report), pass --report PATH --label TEXT.

Needs ffmpeg on PATH, Pillow, and Playwright with Chromium.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

WIDTH, HEIGHT, FPS = 1280, 720, 30
# Identical for every scene so that the files can be joined without re-encoding.
ENCODER_ARGS = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-r", str(FPS), "-video_track_timescale", "15360", "-an"]

SAMPLE_LABEL = "Demo data: bundled fictional sample sites, served on this machine"
SPED_UP_LABEL = "sped up: pauses between requests shortened"
CLOSING_TITLE = "Agent Scout"
CLOSING_LINES = ("Every value links to the sentence it came from.",
                 "What a site does not say stays unknown.")
COMMAND = "agent-scout run sites.yaml -o reports"

MAX_GAP_SECONDS = 0.3        # longer waits between console lines are shortened to this
TYPING_CHARS_PER_SECOND = 22
LABEL_HEIGHT = 40

# terminal look
TERM_BG, TERM_FG, TERM_DIM = (16, 20, 24), (214, 222, 230), (140, 152, 163)
TERM_GREEN, TERM_AMBER, TERM_WHITE = (134, 214, 150), (245, 184, 92), (255, 255, 255)
TERM_FONT_SIZE, TERM_LINE_HEIGHT, TERM_MARGIN = 18, 26, 34

MONO_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
              "/System/Library/Fonts/Menlo.ttc", "C:/Windows/Fonts/consola.ttf", "DejaVuSansMono.ttf"]
MONO_BOLD_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
                   "C:/Windows/Fonts/consolab.ttf", "DejaVuSansMono-Bold.ttf"]
SANS_FONTS = ["/usr/share/fonts/opentype/inter/Inter-Medium.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf",
              "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans.ttf"]
SANS_BOLD_FONTS = ["/usr/share/fonts/opentype/inter/Inter-Bold.otf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                   "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans-Bold.ttf"]
SERIF_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "C:/Windows/Fonts/georgia.ttf",
               "/System/Library/Fonts/Supplemental/Georgia.ttf", "DejaVuSerif.ttf"]


def load_font(candidates: list[str], size: int) -> ImageFont.ImageFont:
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# --------------------------------------------------------------------------- timeline (pure logic)
def compress_timeline(stamps: list[float], max_gap: float = MAX_GAP_SECONDS
                      ) -> tuple[list[float], list[tuple[float, float]]]:
    """Shorten every wait longer than ``max_gap`` to ``max_gap``.

    ``stamps`` are the seconds at which each console line appeared. Returns
    the new stamps (starting at 0) and the intervals of the new timeline that
    stand for a shortened wait, so that the picture can say "sped up" then.
    """
    new_stamps: list[float] = []
    shortened: list[tuple[float, float]] = []
    previous_real = stamps[0] if stamps else 0.0
    now = 0.0
    for stamp in stamps:
        gap = max(0.0, stamp - previous_real)
        if gap > max_gap:
            shortened.append((round(now, 4), round(now + max_gap, 4)))
            gap = max_gap
        now += gap
        new_stamps.append(round(now, 4))
        previous_real = stamp
    return new_stamps, shortened


def wrap(line: str, columns: int) -> list[str]:
    """Wrap one console line to the terminal width: break at a space where
    there is one, and indent continuation rows like the line itself."""
    if len(line) <= columns:
        return [line]
    indent = line[:len(line) - len(line.lstrip(" "))]
    rows, rest = [], line
    while len(rest) > columns:
        cut = rest.rfind(" ", len(indent) + 1, columns + 1)
        if cut <= len(indent):
            cut = columns                      # a single unbroken word longer than the row
        rows.append(rest[:cut].rstrip())
        rest = indent + rest[cut:].lstrip(" ")
    rows.append(rest)
    return rows


@dataclass
class TerminalState:
    typed: str            # how much of the command is on screen
    lines: list[str]      # console lines visible so far
    sped_up: bool         # a shortened wait is being shown


def terminal_states(command: str, lines: list[str], stamps: list[float], *, lead_in: float = 0.5,
                    after_typing: float = 0.5, hold: float = 1.6, fps: int = FPS) -> list[TerminalState]:
    """One state per video frame for scene 1: type the command, then replay
    the recorded lines on the compressed timeline, then hold the last frame."""
    new_stamps, shortened = compress_timeline(stamps)
    typing_seconds = len(command) / TYPING_CHARS_PER_SECOND
    output_start = lead_in + typing_seconds + after_typing
    total = output_start + (new_stamps[-1] if new_stamps else 0.0) + hold
    states = []
    for frame in range(int(round(total * fps))):
        t = frame / fps
        typed = command[:max(0, min(len(command), int((t - lead_in) * TYPING_CHARS_PER_SECOND)))]
        local = t - output_start
        visible = [line for line, stamp in zip(lines, new_stamps) if stamp <= local] if local >= 0 else []
        sped_up = any(start <= local < end for start, end in shortened)
        states.append(TerminalState(typed, visible, sped_up))
    return states


def ease(fraction: float) -> float:
    """Ease-in-out cubic, 0..1 -> 0..1."""
    fraction = min(1.0, max(0.0, fraction))
    return 4 * fraction ** 3 if fraction < 0.5 else 1 - (-2 * fraction + 2) ** 3 / 2


def scroll_positions(start: float, end: float, seconds: float, fps: int = FPS) -> list[int]:
    """Page scroll offsets for a smooth scroll, one per frame, ending exactly at ``end``."""
    frames = max(1, int(round(seconds * fps)))
    return [int(round(start + (end - start) * ease((index + 1) / frames))) for index in range(frames)]


def line_colour(line: str) -> tuple[int, int, int]:
    stripped = line.strip()
    if stripped.startswith("["):
        return TERM_WHITE
    if stripped.startswith("ok:"):
        return TERM_GREEN
    if any(word in stripped for word in ("blocked", "robots_disallowed", "partial:", "off limits",
                                         "JavaScript shell", "every field is unknown")):
        return TERM_AMBER
    if stripped.startswith(("robots.txt", "Reports:", "Log:")):
        return TERM_DIM
    return TERM_FG


# --------------------------------------------------------------------------- drawing
def draw_label(image: Image.Image, text: str, right_text: str = "") -> None:
    """The caption strip at the bottom of scenes 1 and 2."""
    draw = ImageDraw.Draw(image, "RGBA")
    top = image.height - LABEL_HEIGHT
    draw.rectangle([0, top, image.width, image.height], fill=(23, 32, 27, 255))
    font = load_font(SANS_FONTS, 17)
    draw.text((TERM_MARGIN, top + LABEL_HEIGHT // 2), text, font=font, fill=(255, 236, 128, 255), anchor="lm")
    if right_text:
        draw.text((image.width - TERM_MARGIN, top + LABEL_HEIGHT // 2), right_text, font=font,
                  fill=(255, 255, 255, 255), anchor="rm")


def label_overlay(text: str) -> Image.Image:
    """A transparent 1280x720 image with only the caption strip, for ffmpeg's overlay filter."""
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_label(image, text)
    return image


def terminal_geometry() -> tuple[int, int]:
    """(columns, rows) that fit the terminal area."""
    font = load_font(MONO_FONTS, TERM_FONT_SIZE)
    char_width = font.getlength("M")
    columns = int((WIDTH - 2 * TERM_MARGIN) // char_width)
    rows = (HEIGHT - LABEL_HEIGHT - 2 * 22) // TERM_LINE_HEIGHT
    return columns, rows


def render_terminal(state: TerminalState, command: str = COMMAND, label: str = SAMPLE_LABEL) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), TERM_BG)
    draw = ImageDraw.Draw(image)
    font = load_font(MONO_FONTS, TERM_FONT_SIZE)
    bold = load_font(MONO_BOLD_FONTS, TERM_FONT_SIZE)
    columns, rows = terminal_geometry()

    wrapped: list[tuple[str, tuple[int, int, int], bool]] = []
    prompt = "$ " + state.typed
    cursor = len(state.typed) < len(command) or not state.lines
    for piece in wrap(prompt + ("\u2588" if cursor else ""), columns):
        wrapped.append((piece, TERM_WHITE, False))
    for line in state.lines:
        colour = line_colour(line)
        for piece in wrap(line, columns):
            wrapped.append((piece, colour, colour == TERM_WHITE))
    y = 22
    for text, colour, is_bold in wrapped[-rows:]:
        if text.startswith("$ ") and colour == TERM_WHITE and not is_bold:
            draw.text((TERM_MARGIN, y), "$", font=bold, fill=TERM_GREEN)
            draw.text((TERM_MARGIN + font.getlength("$ "), y), text[2:], font=font, fill=TERM_WHITE)
        else:
            draw.text((TERM_MARGIN, y), text, font=bold if is_bold else font, fill=colour)
        y += TERM_LINE_HEIGHT
    draw_label(image, label, SPED_UP_LABEL if state.sped_up else "")
    return image


def render_closing_card() -> Image.Image:
    paper, ink, mark = (243, 245, 241), (23, 32, 27), (255, 236, 128)
    image = Image.new("RGB", (WIDTH, HEIGHT), paper)
    draw = ImageDraw.Draw(image)
    title_font = load_font(SANS_BOLD_FONTS, 84)
    line_font = load_font(SERIF_FONTS, 34)
    draw.text((110, 215), CLOSING_TITLE, font=title_font, fill=ink)
    draw.rectangle([110, 330, WIDTH - 110, 333], fill=ink)
    y = 375
    for index, line in enumerate(CLOSING_LINES):
        box = draw.textbbox((116, y), line, font=line_font)
        if index == 0:
            draw.rectangle([box[0] - 8, box[1] - 7, box[2] + 8, box[3] + 9], fill=mark)
        draw.text((116, y), line, font=line_font, fill=ink)
        y += 64
    return image


# --------------------------------------------------------------------------- ffmpeg
def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise SystemExit("make_demo_video: ffmpeg was not found on PATH")
    return path


def raw_scene_command(output: Path) -> list[str]:
    """Encode raw RGB frames arriving on stdin."""
    return [ffmpeg_path(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", "-", *ENCODER_ARGS, str(output)]


def jpeg_scene_command(output: Path, overlay: Path) -> list[str]:
    """Encode JPEG screenshots arriving on stdin, with the caption strip laid over them."""
    return [ffmpeg_path(), "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg",
            "-framerate", str(FPS), "-i", "-", "-i", str(overlay),
            "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]", "-map", "[v]",
            *ENCODER_ARGS, str(output)]


def still_scene_command(image: Path, seconds: float, output: Path) -> list[str]:
    """A held still, decoded once and repeated."""
    return [ffmpeg_path(), "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(image),
            "-vf", f"format=yuv420p,loop=-1:1,trim=duration={seconds:g}", *ENCODER_ARGS, str(output)]


def concat_command(list_file: Path, output: Path) -> list[str]:
    return [ffmpeg_path(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", str(output)]


def concat_list(scenes: list[Path]) -> str:
    return "".join(f"file '{scene.resolve().as_posix()}'\n" for scene in scenes)


GIF_MAX_BYTES = 8_000_000


def gif_commands(video: Path, palette: Path, output: Path, fps: int = 10, width: int = 960,
                 colours: int = 256) -> list[list[str]]:
    """Two passes: build a palette from the whole video, then use it."""
    scale = f"fps={fps},scale={width}:-1:flags=lanczos"
    return [
        [ffmpeg_path(), "-y", "-loglevel", "error", "-i", str(video), "-vf",
         f"{scale},palettegen=stats_mode=diff:max_colors={colours}", str(palette)],
        [ffmpeg_path(), "-y", "-loglevel", "error", "-i", str(video), "-i", str(palette), "-lavfi",
         f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", str(output)],
    ]


def run_to_file(command: list[str], output: Path, feed=None) -> None:
    """Run ffmpeg writing to a temporary name that still ends in the real
    extension, and rename it only when ffmpeg exits 0."""
    temporary = output.with_name(f"partial-{output.name}")
    command = [*command[:-1], str(temporary)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE if feed else None)
    try:
        if feed:
            feed(process.stdin)
            process.stdin.close()
        code = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if code != 0:
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"make_demo_video: ffmpeg failed with code {code} while writing {output.name}")
    temporary.replace(output)


# --------------------------------------------------------------------------- capture (scene 1 input)
def capture_run(work: Path) -> tuple[list[str], list[float]]:
    """Run the tool on the bundled sample sites; return its console lines and
    the second at which each one appeared. Leaves the reports in work/reports."""
    from fixture_server import FixtureSites

    with FixtureSites(base_port=8641) as sites:
        (work / "sites.yaml").write_text(sites.sites_yaml(), encoding="utf-8", newline="\n")
        environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "agent_scout", "run", "sites.yaml", "-o", "reports"],
            cwd=work, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8")
        lines, stamps = [], []
        began = time.monotonic()
        for line in process.stdout:
            lines.append(line.rstrip("\n"))
            stamps.append(time.monotonic() - began)
        if process.wait() != 0:
            raise SystemExit("make_demo_video: the tool failed on the sample sites:\n" + "\n".join(lines))
    return lines, stamps


def encode_terminal_scene(lines: list[str], stamps: list[float], output: Path) -> int:
    states = terminal_states(COMMAND, lines, stamps)

    def feed(pipe) -> None:
        previous, data = None, b""
        for state in states:
            key = (state.typed, len(state.lines), state.sped_up)
            if key != previous:                 # redraw only when the picture changes
                data = render_terminal(state).tobytes()
                previous = key
            pipe.write(data)

    run_to_file(raw_scene_command(output), output, feed)
    return len(states)


# --------------------------------------------------------------------------- scene 2 (the report in a browser)
def film_report(report: Path, label: str, output: Path, work: Path, preview: Path | None = None) -> int:
    """Film report.html: top, comparison table, one profile, a site that was not read."""
    from playwright.sync_api import sync_playwright

    overlay = work / "label.png"
    label_overlay(label).save(overlay)
    frames: list[bytes] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.goto(report.resolve().as_uri())
        position = {"y": 0}

        def shot() -> bytes:
            return page.screenshot(type="jpeg", quality=92)

        def hold(seconds: float) -> None:
            frames.extend([shot()] * int(round(seconds * FPS)))

        def scroll_to(target: float, seconds: float) -> None:
            limit = page.evaluate("document.documentElement.scrollHeight - window.innerHeight")
            target = max(0, min(int(target), limit))
            for y in scroll_positions(position["y"], target, seconds):
                page.evaluate("y => window.scrollTo(0, y)", y)
                frames.append(shot())
            position["y"] = target

        def top_of(selector: str) -> float | None:
            return page.evaluate(
                "s => { const e = document.querySelector(s); "
                "return e ? e.getBoundingClientRect().top + window.scrollY : null; }", selector)

        def keep(name: str) -> None:
            if preview is not None:
                image = Image.open(io.BytesIO(shot())).convert("RGBA")
                image.alpha_composite(label_overlay(label))
                image.convert("RGB").save(preview / f"scene2-{name}.jpg", quality=92)

        def edges(selector: str) -> tuple[float, float] | None:
            return page.evaluate(
                "s => { const all = document.querySelectorAll(s); if (!all.length) return null; "
                "const first = all[0].getBoundingClientRect(), last = all[all.length - 1].getBoundingClientRect(); "
                "return [first.top + window.scrollY, last.bottom + window.scrollY]; }", selector)

        clear = HEIGHT - LABEL_HEIGHT - 14                      # page height not covered by the caption strip

        hold(2.2)                                              # summary and coverage
        keep("top")
        table = edges("#comparison") or (0, 0)
        heading_stop = table[0] - 96                           # the table with its heading and filters
        scroll_to(heading_stop, 1.0)
        hold(1.8)
        keep("table")
        whole_table_stop = max(heading_stop, table[1] - clear)  # the last row clear of the caption strip
        if whole_table_stop > heading_stop + 4:
            scroll_to(whole_table_stop, 0.8)
        hold(2.0)
        keep("table-lower")

        first = page.query_selector("#comparison tbody tr:not(.not-read) a.open-card")
        if first is not None:
            card = first.get_attribute("href")
            page.evaluate("s => { document.querySelector(s).open = true; }", card)
            scroll_to((top_of(card) or 0) - 12, 1.0)           # the profile, opened
            hold(2.4)
            keep("profile")
            field = page.evaluate(
                "s => { const rows = [...document.querySelectorAll(s + ' .field')].filter(r => r.querySelector('q')); "
                "const pick = rows.find(r => r.dataset.field === 'can_execute') || rows[rows.length - 1]; "
                "return pick ? '#' + pick.id : null; }", card)
            if field:
                scroll_to((top_of(field) or 0) - 16, 1.2)      # one value with its quote and source link
                page.evaluate("h => { location.hash = h; }", field)   # what following a table value does
                hold(2.8)
                keep("evidence")

        unread = edges("#comparison tr.not-read")
        if unread is not None:
            scroll_to(max(unread[0] - 260, unread[1] - clear), 1.2)   # the sites that could not be read
            hold(3.0)
            keep("not-read")
        else:
            scroll_to(heading_stop, 1.2)
            hold(2.0)
        browser.close()

    def feed(pipe) -> None:
        for frame in frames:
            pipe.write(frame)

    run_to_file(jpeg_scene_command(output, overlay), output, feed)
    return len(frames)


# --------------------------------------------------------------------------- main
def probe_seconds(video: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return -1.0
    done = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                           str(video)], capture_output=True, text=True)
    return float(done.stdout.strip() or -1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs", help="directory for demo.mp4 and demo.gif")
    parser.add_argument("--report", type=Path,
                        help="film this report.html in scene 2 instead of the sample run's report")
    parser.add_argument("--label", default=SAMPLE_LABEL,
                        help="caption shown during scene 2 (say what data the report holds)")
    parser.add_argument("--preview", type=Path,
                        help="only write still frames of the busiest moments into this directory")
    parser.add_argument("--keep-build", type=Path, help="keep scene files and the sample run in this directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.report is not None and args.label == SAMPLE_LABEL:
        raise SystemExit("make_demo_video: --report needs --label saying what that report shows")
    work = args.keep_build or Path(tempfile.mkdtemp(prefix="agent-scout-video-"))
    work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    print("Running the tool on the bundled fictional sample sites (default settings, about 30 seconds)...")
    lines, stamps = capture_run(work)
    report = args.report or work / "reports" / "report.html"

    if args.preview is not None:
        args.preview.mkdir(parents=True, exist_ok=True)
        states = terminal_states(COMMAND, lines, stamps)
        busiest = max(range(len(states)), key=lambda index: (len(states[index].lines), -index))
        middle = next(index for index, state in enumerate(states) if len(state.lines) >= len(lines) // 2)
        typing = next(index for index, state in enumerate(states) if len(state.typed) >= len(COMMAND) // 2)
        speeding = next((index for index, state in enumerate(states) if state.sped_up), middle)
        for name, index in (("typing", typing), ("sped-up", speeding), ("middle", middle), ("end", busiest)):
            render_terminal(states[index]).save(args.preview / f"scene1-{name}.jpg", quality=92)
        film_report(report, args.label, work / "preview-scene2.mp4", work, preview=args.preview)
        render_closing_card().save(args.preview / "scene3.jpg", quality=95)
        print(f"Preview frames written to {args.preview}")
        return 0

    scenes = [work / "scene1.mp4", work / "scene2.mp4", work / "scene3.mp4"]
    print("Scene 1: terminal...")
    encode_terminal_scene(lines, stamps, scenes[0])
    print("Scene 2: filming the report...")
    film_report(report, args.label, scenes[1], work)
    print("Scene 3: closing card...")
    still = work / "closing.jpg"
    render_closing_card().save(still, quality=95)
    run_to_file(still_scene_command(still, 2.0, scenes[2]), scenes[2])

    list_file = work / "scenes.txt"
    list_file.write_text(concat_list(scenes), encoding="utf-8")
    video = args.out / "demo.mp4"
    run_to_file(concat_command(list_file, video), video)
    gif = args.out / "demo.gif"
    for colours in (256, 128, 64):                 # fewer colours only if the preview would exceed 8 MB
        first_pass, second_pass = gif_commands(video, work / "palette.png", gif, colours=colours)
        subprocess.run(first_pass, check=True)
        run_to_file(second_pass, gif)
        if gif.stat().st_size <= GIF_MAX_BYTES:
            break

    seconds = probe_seconds(video)
    print(f"Wrote {video} ({seconds:.1f} s, {video.stat().st_size / 1e6:.1f} MB) and "
          f"{gif} ({gif.stat().st_size / 1e6:.1f} MB)")
    if not args.keep_build:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
