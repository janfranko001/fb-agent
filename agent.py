"""Estetic Center of New York — Facebook post automation.

Flow: OpenAI writes post text + image prompt -> OpenAI generates the image -> Facebook Graph API publishes.

Usage:
    python agent.py generate            # create the next post (text + image), save as pending
    python agent.py generate --topic "პილინგი"
    python agent.py publish <post.json> # publish a saved post
    python agent.py run                 # generate, then publish if AUTO_PUBLISH=true
"""
import argparse
import base64
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
POSTS = ROOT / "posts"
IMAGES = ROOT / "images"

load_dotenv(ROOT / ".env")

TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2")
GRAPH = "https://graph.facebook.com/v21.0"

# Topics rotate in order; the brand facts themselves come from CLAUDE.md.
TOPICS = [
    "Deep facial cleansing",
    "A simple daily skincare routine tip",
    "Facial peeling",
    "Relaxing facial massage",
    "Eyebrow shaping",
    "Why we use only high-quality products",
    "Our experienced specialists",
    "How to book a visit (app or phone)",
]

PROMPT = """Create a new Facebook post about: {topic}

Return only JSON (no other text) in this format:
{{"post_text": "...", "image_prompt": "..."}}

- post_text: written in natural, fluent English, following the rules and brand facts in the instructions above (use only the prices and contact details given there). The call to action must offer booking via the app or by phone. Use only common, real hashtags.
  Format post_text beautifully, with line breaks (\\n) and a blank line between blocks, each block starting on a new line:
  1) a catchy headline line starting with one emoji;
  2) 1-2 short lines of warm description (one idea per line);
  3) optionally 2-3 benefit lines, each starting on its own line with a small emoji (for example ✨ or 🌸);
  4) a call-to-action block: a line inviting to book via our app or by phone, then "📞 <phone number>" and "📍 Brooklyn, New York" each on its own line;
  5) a final line with the 3-5 hashtags.
  No long paragraphs, never one solid block of text.
- image_prompt: a detailed photo description in English (subject, style, lighting, colors, composition), square 1:1 for a feed post, with no text or lettering in the image. Explicitly state that there must be no logos, brand names, labels, signs or writing anywhere: uniforms, bottles and jars must be plain and unbranded."""


def write_post_text(topic: str) -> dict:
    client = OpenAI()
    system = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    res = client.chat.completions.create(
        model=TEXT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": PROMPT.format(topic=topic)},
        ],
    )
    return json.loads(res.choices[0].message.content)


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def brand_image(path: Path) -> None:
    """Put the photo in an elegant frame and add the brand name + phone in the bottom-left corner."""
    size, margin = 1080, 44
    cream, gold = (250, 244, 236), (191, 155, 88)
    canvas = Image.new("RGB", (size, size), cream)
    draw = ImageDraw.Draw(canvas)

    inner = size - 2 * margin
    photo = Image.open(path).convert("RGB").resize((inner, inner), Image.LANCZOS)
    canvas.paste(photo, (margin, margin))

    # double gold frame: thin outer line on the cream mat + a line right around the photo
    draw.rectangle([10, 10, size - 11, size - 11], outline=gold, width=3)
    draw.rectangle([margin - 3, margin - 3, size - margin + 2, size - margin + 2], outline=gold, width=3)

    # corner label (semi-transparent cream card)
    serif = ["georgiab.ttf", "Georgia Bold.ttf", str(ROOT / "fonts" / "Lora-Bold.ttf"), "DejaVuSerif-Bold.ttf"]
    sans = ["segoeui.ttf", "Arial.ttf", str(ROOT / "fonts" / "OpenSans.ttf"), "DejaVuSans.ttf"]
    name_font, phone_font = _font(serif, 34), _font(sans, 28)
    name, phone = "Estetic Center of New York", "Tel: 111 111 1111"
    pad = 22
    w = max(draw.textlength(name, font=name_font), draw.textlength(phone, font=phone_font)) + 2 * pad
    h = 34 + 28 + 3 * pad - 4
    x0, y1 = margin + 26, size - margin - 26
    y0 = y1 - h
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([x0, y0, x0 + w, y1], radius=16, fill=(250, 244, 236, 225), outline=gold + (255,), width=2)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)
    draw.text((x0 + pad, y0 + pad - 4), name, font=name_font, fill=(92, 64, 40))
    draw.text((x0 + pad, y0 + pad + 34 + 6), phone, font=phone_font, fill=(150, 110, 50))
    canvas.convert("RGB").save(path)


def make_image(prompt: str, path: Path) -> None:
    client = OpenAI()
    prompt += " Absolutely no text, letters, logos, brand names or labels anywhere; all clothing, bottles and packaging plain and unbranded."
    res = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size="1024x1024", quality="medium")
    path.write_bytes(base64.b64decode(res.data[0].b64_json))
    brand_image(path)


def generate(topic: str | None) -> Path:
    POSTS.mkdir(exist_ok=True)
    IMAGES.mkdir(exist_ok=True)
    if topic is None:
        # stateless rotation (works on hosts with an ephemeral disk): one topic per calendar day
        topic = TOPICS[datetime.now().toordinal() % len(TOPICS)]

    content = write_post_text(topic)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    image_path = IMAGES / f"{stamp}.png"
    make_image(content["image_prompt"], image_path)

    post_path = POSTS / f"{stamp}.json"
    post_path.write_text(
        json.dumps(
            {
                "topic": topic,
                "post_text": content["post_text"],
                "image_prompt": content["image_prompt"],
                "image": str(image_path.relative_to(ROOT)),
                "status": "pending",
                "fb_post_id": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"შეიქმნა: {post_path}")
    return post_path


def publish(post_path: Path) -> None:
    page_id = os.environ["FB_PAGE_ID"]
    token = os.environ["FB_PAGE_TOKEN"]
    post = json.loads(post_path.read_text(encoding="utf-8"))
    if post["status"] == "published":
        print("უკვე გამოქვეყნებულია.")
        return
    with open(ROOT / post["image"], "rb") as f:
        r = requests.post(
            f"{GRAPH}/{page_id}/photos",
            data={"message": post["post_text"], "access_token": token},
            files={"source": f},
            timeout=120,
        )
    r.raise_for_status()
    post["status"] = "published"
    post["fb_post_id"] = r.json().get("post_id") or r.json().get("id")
    post_path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"გამოქვეყნდა: {post['fb_post_id']}")

    try:
        post["fb_story_id"] = publish_story(ROOT / post["image"], page_id, token)
        print(f"სთორი გამოქვეყნდა: {post['fb_story_id']}")
    except Exception as e:  # the feed post is already live; don't fail the run over the story
        post["fb_story_id"] = None
        print(f"სთორი ვერ გამოქვეყნდა: {e}")
    post_path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")


def story_image(src: Path, dst: Path) -> None:
    """9:16 story canvas (1080x1920) with the framed post image centered on a cream background."""
    canvas = Image.new("RGB", (1080, 1920), (250, 244, 236))
    canvas.paste(Image.open(src).convert("RGB"), (0, (1920 - 1080) // 2))
    canvas.save(dst)


def story_video(image_path: Path, music: Path, out: Path, seconds: int = 15) -> None:
    """9:16 MP4 of the story image with a random slice of the track and a short fade-out."""
    import random
    import subprocess

    import imageio_ffmpeg

    story_path = image_path.with_name(image_path.stem + "-story.png")
    story_image(image_path, story_path)
    start = random.randint(0, 30)
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(story_path), "-ss", str(start), "-i", str(music),
            "-t", str(seconds), "-af", f"afade=t=in:d=0.5,afade=t=out:st={seconds - 1.5}:d=1.5",
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-shortest", str(out),
        ],
        check=True,
    )


def publish_story(image_path: Path, page_id: str, token: str) -> str:
    tracks = sorted((ROOT / "music").glob("*.mp3"))
    if tracks:
        return publish_video_story(image_path, random.choice(tracks), page_id, token)
    return publish_photo_story(image_path, page_id, token)


def publish_video_story(image_path: Path, music: Path, page_id: str, token: str) -> str:
    video = image_path.with_name(image_path.stem + "-story.mp4")
    story_video(image_path, music, video)
    r = requests.post(
        f"{GRAPH}/{page_id}/video_stories",
        data={"upload_phase": "start", "access_token": token},
        timeout=120,
    )
    r.raise_for_status()
    video_id, upload_url = r.json()["video_id"], r.json()["upload_url"]
    data = video.read_bytes()
    r = requests.post(
        upload_url,
        headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))},
        data=data,
        timeout=300,
    )
    r.raise_for_status()
    r = requests.post(
        f"{GRAPH}/{page_id}/video_stories",
        data={"upload_phase": "finish", "video_id": video_id, "access_token": token},
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("post_id") or video_id


def publish_photo_story(image_path: Path, page_id: str, token: str) -> str:
    story_path = image_path.with_name(image_path.stem + "-story.png")
    story_image(image_path, story_path)
    with open(story_path, "rb") as f:
        r = requests.post(
            f"{GRAPH}/{page_id}/photos",
            data={"published": "false", "access_token": token},
            files={"source": f},
            timeout=120,
        )
    r.raise_for_status()
    r = requests.post(
        f"{GRAPH}/{page_id}/photo_stories",
        data={"photo_id": r.json()["id"], "access_token": token},
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("post_id") or r.json().get("id")


def run_once() -> None:
    path = generate(None)
    if os.getenv("AUTO_PUBLISH", "false").lower() == "true":
        publish(path)
    else:
        print("AUTO_PUBLISH=false — პოსტი ელოდება დამტკიცებას. გამოსაქვეყნებლად: python agent.py publish", path)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--topic")
    p = sub.add_parser("publish")
    p.add_argument("post")
    sub.add_parser("run")
    args = ap.parse_args()

    if args.cmd == "generate":
        generate(args.topic)
    elif args.cmd == "publish":
        publish(Path(args.post))
    else:
        run_once()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    sys.exit(main())
