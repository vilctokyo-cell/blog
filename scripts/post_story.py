"""ストーリー+挿絵を生成してJekyllブログ記事として保存し、GitHubへpushする。

使い方:
    python3 scripts/post_story.py ["テーマ・方向性"] [--no-push]

- ストーリー: Gemini (generate_story.py)。全5話の連載として、実行のたびに1話ずつ進む。
- 挿絵: Pollinations.ai (アニメ風オリジナルキャラ、露出なし、毎回ランダムな見た目)
- 記事: _posts/YYYY-MM-DD-slug.md に保存、画像は assets/images/posts/ に保存
- 連載の進行状況は data/series_state.json に保存し、5話目で完結すると自動的にリセットされる
- 最後に git add/commit/push (リモート未設定や失敗時はエラー報告)
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import random
import re
import subprocess
import sys
import urllib.parse

import requests
from PIL import Image

from generate_story import generate_story
from pixai_image import generate_image as pixai_generate_image
from draw_things_image import generate_image as draw_things_generate_image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE_PATH = os.path.join(REPO_ROOT, "data", "series_state.json")

IMAGE_BASE = (
    "anime style illustration, cute girl character, upper body portrait shot, chest-up composition, "
    "moe aesthetic, clean sharp line art, vivid colors, big sparkling expressive eyes, "
    "soft cel shading, Japanese anime art style, high quality detailed illustration, "
    "generous headroom with margin above the head, entire face and both eyes clearly visible, "
    "top of head fully in frame, not zoomed in, not an extreme close-up, "
    "hands and arms not visible in frame, no hands shown"
)
IMAGE_MODESTY_NOTE = (
    "(high crew neckline, turtleneck-style collar:1.3), (shoulders fully covered by fabric:1.3), "
    "(sleeves covering the shoulders and upper arms:1.3), never sleeveless, never strapless, never off-shoulder, "
    "single unified one-piece garment with a fully closed hem, "
    "stomach and waist completely covered by fabric with no visible skin between chest and thighs, "
    "no visible collarbone, no visible cleavage, hem reaching the knees"
)
HAIR_COLORS = ["black", "silver", "pastel pink", "light blue", "honey blonde", "lavender purple", "chestnut brown"]
HAIRSTYLES = ["long straight hair", "twin tails", "high ponytail", "short bob cut", "wavy shoulder-length hair", "hair in a high bun with ribbon"]
OUTFITS = [
    "long band t-shirt dress reaching mid-thigh with a wide belt, paired with leggings",
    "long tunic-length dress with band merch print, closed hem falling well past the hips, paired with leggings",
    "long-sleeve turtleneck knee-length dress",
    "sailor-style knee-length dress with a wide collar and knee-high socks",
]
POSES = [
    "bright cheerful smile looking straight at the camera, dynamic stage lighting with spotlights",
    "playful wink with head tilted slightly, joyful expression",
    "surprised expression with mouth open, sparkling eyes",
    "gentle closed-eye smile, peaceful expression",
    "laughing joyfully with eyes closed, head tilted back slightly",
    "shy smile looking sideways, soft blush",
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
        IMAGE_MODESTY_NOTE,
        f"{random.choice(HAIR_COLORS)} {random.choice(HAIRSTYLES)}",
        random.choice(OUTFITS),
        random.choice(POSES),
        random.choice(BACKGROUNDS),
    ]
    return ", ".join(parts)


def generate_image(prompt: str, out_path: str, retries: int = 3) -> str:
    """ローカルのDraw Things(Anime Anything v3)を優先使用する。Pollinationsはアニメ塗りから
    半端にリアルな3D調へ style drift しやすく(不気味の谷)、服装指示も守られないことがあったため。
    Draw Things.appが起動していない/APIサーバーがOFFの場合はPixAI、それも無ければPollinationsに
    フォールバックする。どの経路でも最終的に768px幅のJPEGに圧縮して保存する。"""
    try:
        raw_path = out_path + ".dt_raw.png"
        draw_things_generate_image(prompt, raw_path)
        img = Image.open(raw_path).convert("RGB")
        img.thumbnail((768, 768))
        img.save(out_path, "JPEG", quality=82, optimize=True)
        os.remove(raw_path)
        return out_path
    except Exception:
        pass  # Draw Things未起動・失敗時はPixAI/Pollinationsにフォールバック

    if os.environ.get("PIXAI_API_KEY"):
        try:
            raw_path = out_path + ".pixai_raw.png"
            pixai_generate_image(prompt, raw_path)
            img = Image.open(raw_path).convert("RGB")
            img.thumbnail((768, 768))
            img.save(out_path, "JPEG", quality=82, optimize=True)
            os.remove(raw_path)
            return out_path
        except Exception:
            pass  # PixAI失敗時はPollinationsにフォールバック

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


def load_state() -> dict | None:
    if not os.path.exists(STATE_PATH):
        return None
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clear_state() -> None:
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)


def safe_slug(slug: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", slug.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or f"story-{int(datetime.datetime.now().timestamp())}"


def body_to_markdown(body: str) -> str:
    """本文をMarkdown段落に整える(連続改行は段落、単独改行はそのまま=hard_wrapで<br>)。"""
    return body.strip()


def run(theme: str, push: bool):
    now = datetime.datetime.now()

    state = load_state()

    print("1/3 ストーリー生成中...", file=sys.stderr)
    story = generate_story(theme, state=state)
    episode = story["episode"]
    is_final = story["is_final"]

    if state is None:
        series_slug = safe_slug(story["slug"])
    else:
        series_slug = state["series_slug"]
    slug = f"{series_slug}-ep{episode}"

    title_prefix = f"【全{story['total_episodes']}話・完結】" if is_final else f"【全{story['total_episodes']}話・第{episode}話】"
    title = f"{title_prefix}{story['title']}"
    print(f"  タイトル: {title} (slug: {slug})", file=sys.stderr)

    print("2/3 挿絵生成中...", file=sys.stderr)
    image_rel = f"assets/images/posts/{now:%Y-%m-%d}-{slug}.jpg"
    generate_image(build_image_prompt(), os.path.join(REPO_ROOT, image_rel))

    print("3/3 記事ファイル作成中...", file=sys.stderr)
    description = re.sub(r"\s+", " ", story["body"]).strip()[:90]
    front_matter = "\n".join([
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
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

    if is_final:
        clear_state()
    else:
        save_state({
            "series_slug": series_slug,
            "protagonist_name": story["protagonist_name"],
            "band_name": story["band_name"],
            "pattern_name": story["pattern_name"],
            "pattern_desc": story["pattern_desc"],
            "episode": episode + 1,
            "summary_so_far": story["episode_summary"],
        })

    if push:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"post: {title}"],
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
    print(f"タイトル: {title}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("theme", nargs="?", default="")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()
    run(args.theme, push=not args.no_push)
