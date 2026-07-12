"""ストーリー+挿絵を生成してJekyllブログ記事として保存し、GitHubへpushする。

使い方:
    python3 scripts/post_story.py ["テーマ・方向性"] [--no-push]

- ストーリー: Gemini (generate_story.py)
- 挿絵: Pollinations.ai (アニメ風オリジナルキャラ、露出なし、毎回ランダムな見た目)
- 記事: _posts/YYYY-MM-DD-slug.md に保存、画像は assets/images/posts/ に保存
- 最後に git add/commit/push (リモート未設定や失敗時はエラー報告)
"""
import argparse
import datetime
import io
import os
import random
import re
import subprocess
import sys
import urllib.parse

import requests
from PIL import Image

from generate_story import generate_story

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

IMAGE_BASE = (
    "anime style illustration, cute girl character, full body standing pose, "
    "moe aesthetic, clean sharp line art, vivid colors, big sparkling expressive eyes, "
    "soft cel shading, Japanese anime art style, high quality detailed illustration, "
    "full body visible head to feet, precise clean hand anatomy, exactly two arms and two hands"
)
IMAGE_MODESTY_NOTE = "one-piece garment silhouette, single continuous outfit from chest to knees"
HAIR_COLORS = ["black", "silver", "pastel pink", "light blue", "honey blonde", "lavender purple", "chestnut brown"]
HAIRSTYLES = ["long straight hair", "twin tails", "high ponytail", "short bob cut", "wavy shoulder-length hair", "hair in a high bun with ribbon"]
OUTFITS = [
    "long band t-shirt dress reaching mid-thigh with a wide belt, paired with leggings",
    "oversized hoodie dress reaching the knees with band merch print, paired with leggings",
    "flowy knee-length sundress decorated with enamel pin badges and ribbons",
    "long-sleeve turtleneck knee-length dress",
    "denim pinafore dress over a long-sleeve top, knee-length skirt section",
    "sailor-style knee-length dress with a wide collar and knee-high socks",
]
POSES = [
    "holding a glow stick high, dynamic stage lighting with spotlights, energetic rock performance pose",
    "peace sign pose with a bright cheerful smile",
    "jumping mid-air with arms raised in excitement",
    "waving both penlights side to side, joyful expression",
    "striking a confident idol pose with sparkles in the background",
    "gentle twirl with skirt flowing, cheerful wink",
]
BACKGROUNDS = [
    "concert stage with colorful spotlights",
    "sea of glow sticks in a dark live venue",
    "outdoor festival stage at sunset",
    "backstage corridor with band posters",
    "starry night sky with stage lights beaming up",
]


def build_image_prompt() -> str:
    parts = [
        IMAGE_BASE,
        f"{random.choice(HAIR_COLORS)} {random.choice(HAIRSTYLES)}",
        random.choice(OUTFITS),
        random.choice(POSES),
        random.choice(BACKGROUNDS),
        IMAGE_MODESTY_NOTE,
    ]
    return ", ".join(parts)


def generate_image(prompt: str, out_path: str, retries: int = 3) -> str:
    """Pollinationsで生成し、768px幅のJPEGに圧縮して保存する。"""
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}"
    last_error = None
    for _ in range(retries):
        seed = random.randint(0, 2**31 - 1)
        try:
            resp = requests.get(
                url,
                params={"width": 1024, "height": 1024, "nologo": "true", "seed": seed},
                timeout=90,
            )
            if resp.status_code >= 300:
                last_error = RuntimeError(f"画像生成失敗 ({resp.status_code})")
                continue
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img.thumbnail((768, 768))
            img.save(out_path, "JPEG", quality=82, optimize=True)
            return out_path
        except Exception as e:  # ネットワーク断・不正画像など
            last_error = e
            continue
    raise last_error


def safe_slug(slug: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", slug.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or f"story-{int(datetime.datetime.now().timestamp())}"


def body_to_markdown(body: str) -> str:
    """本文をMarkdown段落に整える(連続改行は段落、単独改行はそのまま=hard_wrapで<br>)。"""
    return body.strip()


def run(theme: str, push: bool):
    now = datetime.datetime.now()

    print("1/3 ストーリー生成中...", file=sys.stderr)
    story = generate_story(theme)
    slug = safe_slug(story["slug"])
    print(f"  タイトル: {story['title']} (slug: {slug})", file=sys.stderr)

    print("2/3 挿絵生成中...", file=sys.stderr)
    image_rel = f"assets/images/posts/{now:%Y-%m-%d}-{slug}.jpg"
    generate_image(build_image_prompt(), os.path.join(REPO_ROOT, image_rel))

    print("3/3 記事ファイル作成中...", file=sys.stderr)
    description = re.sub(r"\s+", " ", story["body"]).strip()[:90]
    front_matter = "\n".join([
        "---",
        f'title: "{story["title"].replace(chr(34), chr(39))}"',
        f"date: {now:%Y-%m-%d %H:%M:%S} +0900",
        f"slug: {slug}",
        f"image: /{image_rel}",
        f'description: "{description.replace(chr(34), chr(39))}…"',
        "---",
        "",
    ])
    post_rel = f"_posts/{now:%Y-%m-%d}-{slug}.md"
    with open(os.path.join(REPO_ROOT, post_rel), "w") as f:
        f.write(front_matter + body_to_markdown(story["body"]) + "\n")

    if push:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"post: {story['title']}"],
            cwd=REPO_ROOT, check=True,
        )
        result = subprocess.run(
            ["git", "push"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"git push 失敗: {result.stderr.strip()}")
        print(f"完了 (公開): /stories/{slug}/")
    else:
        print(f"完了 (ローカル保存のみ): {post_rel}")
    print(f"タイトル: {story['title']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("theme", nargs="?", default="")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()
    run(args.theme, push=not args.no_push)
