from collections.abc import Callable, Iterator
from fractions import Fraction
from typing import Any, NoReturn
import base64, io, json, sys, wave

lazy import av
lazy from av.container import InputContainer
lazy from av.error import FFmpegError
lazy from av.subtitles.subtitle import AssSubtitle
lazy from av.video.frame import VideoFrame
lazy from PIL import Image, UnidentifiedImageError

RATE    = 16_000
WIDTH   = 2
SIDE    = 1024
EVEN    = 2
SHARP   = 85
FIELDS  = ("title", "description", "comment", "synopsis", "lyrics", "subject", "keywords")
EXIF    = { 0x010E: "description", 0x9C9B: "title", 0x9C9C: "comment", 0x9C9F: "subject", 0x9C9E: "keywords" }
NOTES   = ("Title", "Description", "Comment", "Subject", "Keywords")
UNICODE = b"UNICODE\x00"
ASCII   = b"ASCII\x00\x00\x00"
USER    = 0x9286
DETAILS = 0x8769

def write ( data: bytes ) -> None:

    sys.stdout.buffer.write(data)

def emit ( found: object ) -> None:

    write(json.dumps(found, ensure_ascii=False).encode())

def refuse ( reason: str ) -> NoReturn:

    emit({ "error": reason })

    sys.exit(1)

def spoken ( value: object ) -> str:

    if isinstance(value, str): return value.strip("\x00 ")
    if not isinstance(value, bytes): return ""
    if value.startswith(UNICODE): return value[len(UNICODE):].decode("utf-16-le", "ignore").strip("\x00 ")
    if value.startswith(ASCII): return value[len(ASCII):].decode("ascii", "ignore").strip("\x00 ")

    return value.decode("utf-16-le" if b"\x00" in value else "utf-8", "ignore").strip("\x00 ")

def captions ( image: Image.Image ) -> Iterator[str]:

    tags    = image.getexif()
    details = tags.get_ifd(DETAILS)

    yield from (spoken(tags.get(tag)) for tag in EXIF)
    yield spoken(details.get(USER))
    yield from (spoken(image.info.get(name)) for name in NOTES)

def picture ( data: bytes, limits: dict[str, Any] ) -> dict[str, Any]:

    Image.MAX_IMAGE_PIXELS = int(limits["pixels"])

    try:

        with Image.open(io.BytesIO(data)) as image:

            image.verify()

        with Image.open(io.BytesIO(data)) as image:

            texts = [text for text in dict.fromkeys(captions(image)) if text]
            mime  = Image.MIME.get(image.format or "", limits["mime"])

    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError): refuse("image")

    return { "mime": mime, "parts": [{ "text": text } for text in texts], "gaps": [{ "kind": "vision" }] }

def still ( data: bytes, limits: dict[str, Any] ) -> bytes:

    Image.MAX_IMAGE_PIXELS = int(limits["pixels"])
    buffer = io.BytesIO()

    try:

        with Image.open(io.BytesIO(data)) as image:

            image.thumbnail((SIDE, SIDE))
            image.convert("RGB").save(buffer, "JPEG", quality=SHARP)

    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError): refuse("image")

    return buffer.getvalue()

def opened ( data: bytes ) -> InputContainer:

    try: return av.open(io.BytesIO(data), "r")
    except (FFmpegError, OSError, ValueError): refuse("media")

def subtitles ( container: InputContainer ) -> list[dict[str, Any]]:

    found: list[dict[str, Any]] = []

    for stream in container.streams.subtitles:

        for packet in container.demux(stream):

            if packet.pts is None: continue

            second = float(packet.pts * stream.time_base) if stream.time_base else 0.0

            for cue in packet.decode():

                said = cue.dialogue.decode("utf-8", "ignore").strip() if isinstance(cue, AssSubtitle) else ""

                if said: found.append({ "text": said, "second": round(second, 3) })

    return found

def footage ( data: bytes, limits: dict[str, Any] ) -> dict[str, Any]:

    container = opened(data)

    try:

        length = float(container.duration or 0) / av.time_base

        if length > float(limits["duration"]): refuse("duration")

        tags  = [container.metadata, *(stream.metadata for stream in container.streams)]
        said  = (str(found.get(name, "")).strip() for found in tags for name in FIELDS)
        notes = [{ "text": text } for text in dict.fromkeys(said) if text]
        cues  = subtitles(container)
        heard = bool(container.streams.audio) and not cues
        seen  = bool(container.streams.video)

    except FFmpegError: refuse("media")
    finally: container.close()

    family  = "video" if seen else "audio"
    gaps    = [{ "kind": "speech", "start": 0.0, "end": length }] if heard else []
    gaps   += [{ "kind": "frames", "start": 0.0, "end": length }] if seen else []

    return { "mime": f"{family}/{limits['mime'].split('/')[1]}", "parts": [*notes, *cues], "gaps": gaps }

def clip ( data: bytes, start: float, end: float ) -> bytes:

    container = opened(data)
    sampler   = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    pcm       = bytearray()
    first     : float | None = None

    try:

        if not container.streams.audio: refuse("audio")

        stream = container.streams.audio[0]

        if start > 0 and stream.time_base: container.seek(int(start / stream.time_base), stream=stream)

        for frame in container.decode(stream):

            moment = float(frame.time or 0.0)

            if moment >= end: break
            if moment + frame.samples / (frame.rate or RATE) <= start: continue

            first = moment if first is None else first

            for chunk in sampler.resample(frame): pcm += bytes(chunk.planes[0])[:chunk.samples * WIDTH]

        for chunk in sampler.resample(None): pcm += bytes(chunk.planes[0])[:chunk.samples * WIDTH]

    except FFmpegError: refuse("media")
    finally: container.close()

    skip = max(round((start - (first if first is not None else start)) * RATE), 0) * WIDTH
    size = round((end - start) * RATE) * WIDTH
    pcm  = pcm[skip:skip + size]

    sound = io.BytesIO()

    with wave.open(sound, "wb") as written:

        written.setnchannels(1)
        written.setsampwidth(WIDTH)
        written.setframerate(RATE)
        written.writeframes(bytes(pcm))

    return sound.getvalue()

def jpeg ( frame: VideoFrame ) -> str:

    scale  = min(1.0, SIDE / max(frame.width, frame.height, 1))
    width  = max(EVEN, int(frame.width * scale) // EVEN * EVEN)
    height = max(EVEN, int(frame.height * scale) // EVEN * EVEN)
    codec  = av.CodecContext.create("mjpeg", "w")

    codec.width, codec.height, codec.pix_fmt = width, height, "yuvj420p"
    codec.time_base = Fraction(1, 1)

    packets = [*codec.encode(frame.reformat(width, height, "yuvj420p")), *codec.encode(None)]

    return base64.b64encode(b"".join(bytes(packet) for packet in packets)).decode()

def frames ( data: bytes, moments: list[float] ) -> list[dict[str, Any]]:

    container = opened(data)
    found: list[dict[str, Any]] = []

    try:

        if not container.streams.video: refuse("video")

        stream = container.streams.video[0]

        for moment in moments:

            if stream.time_base: container.seek(int(moment / stream.time_base), stream=stream)

            frame = next((frame for frame in container.decode(stream) if (frame.time or 0.0) >= moment), None)

            if frame is not None: found.append({ "second": round(moment, 3), "data": jpeg(frame) })

    except FFmpegError: refuse("media")
    finally: container.close()

    return found

def read ( data: bytes, limits: dict[str, Any] ) -> dict[str, Any]:

    return picture(data, limits) if limits["mime"].startswith("image/") else footage(data, limits)

ACTIONS: dict[str, Callable[[bytes, dict[str, Any]], None]] = {
    "read"   : lambda data, limits: emit(read(data, limits)),
    "clip"   : lambda data, limits: write(clip(data, float(limits["start"]), float(limits["end"]))),
    "frames" : lambda data, limits: emit(frames(data, [float(moment) for moment in limits["moments"]])),
    "still"  : lambda data, limits: write(still(data, limits)),
}

def main () -> None:

    action, limits = sys.argv[1], json.loads(sys.argv[2])

    if action not in ACTIONS: refuse("action")

    ACTIONS[action](sys.stdin.buffer.read(), limits)

if __name__ == "__main__":

    main()
