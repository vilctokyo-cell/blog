"""Draw Things(Mac版、ローカルHTTP API・APIキー不要)で画像を1枚生成する。

事前準備: 設定 > すべて > APIサーバー で「サーバーオンライン」をON、プロトコルを
「HTTP」にしておくこと(ポート7860)。モデルは "Anime (Anything v3)" を選択して
おく(Animagine XL v3.1はこの環境で生成が崩れる不具合を確認済みのため非推奨)。
アプリ自体が起動していない/APIサーバーに繋がらない場合は generate_image() が
`open -a "Draw Things"` で自動起動し、起動完了(最大 launch_wait 秒)を待ってから
生成を試みる。それでも繋がらなければ例外を投げるので、呼び出し側(post_story.py)
でPixAI/Pollinationsにフォールバックする。

X運用/draw_things_image.py と同じ仕組み。ブログの挿絵は正方形バストアップ構図
なので width/height をそれに合わせて 768x768 にしている点のみ異なる。
"""
import base64
import subprocess
import sys
import time
import requests

BASE_URL = "http://127.0.0.1:7860"
APP_NAME = "Draw Things"

NEGATIVE_PROMPT_DEFAULT = (
    "lowres, bad anatomy, bad hands, missing fingers, extra digit, fewer digits, "
    "cropped, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
    "signature, watermark, username, text, kanji, japanese text, gibberish text, writing, "
    "3d render, cgi, semi-realistic, photorealistic, uncanny, deformed, extra limbs, "
    "(bare shoulders:1.3), (off-shoulder:1.3), off shoulder, strapless, tube top, bandeau, halter top, "
    "sleeveless, (visible cleavage:1.3), (visible collarbone:1.2), bare arms, tank top, camisole, "
    "(extreme close-up:1.4), (cropped face:1.4), (cropped forehead:1.4), (cropped head:1.4), "
    "cut off head, one eye visible, close-up of neck, close-up of chest, close-up of collarbone, exposed skin, "
    "reference sheet, character sheet, multiple views, turnaround, multiple angles, split screen, collage"
)


def _server_is_up() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/sdapi/v1/options", timeout=3)
        return r.status_code < 300
    except Exception:
        return False


def _ensure_running(launch_wait: float = 60.0, poll_interval: float = 2.0) -> None:
    """API未応答ならDraw Things.appをopenコマンドで起動し、応答するまで待つ。
    アプリは起動済みだがプロジェクト未作成/APIサーバーOFFの場合はopenしても直らないため、
    launch_wait経過後は諦めて例外を投げ、呼び出し側のフォールバックに任せる。"""
    if _server_is_up():
        return
    subprocess.run(["open", "-a", APP_NAME], check=False)
    deadline = time.time() + launch_wait
    while time.time() < deadline:
        if _server_is_up():
            return
        time.sleep(poll_interval)
    raise RuntimeError(
        f"{APP_NAME}を自動起動しましたが{launch_wait}秒待ってもAPIサーバーに接続できませんでした"
        "(プロジェクト未作成、またはAPIサーバー設定がOFFの可能性)"
    )


def generate_image(
    prompt: str,
    out_path: str,
    negative_prompt: str = NEGATIVE_PROMPT_DEFAULT,
    width: int = 640,
    height: int = 896,
    steps: int = 32,
    guidance_scale: float = 7.5,
    sampler: str = "Euler a",
    hires_fix: bool = True,
    hires_fix_width: int = 448,
    hires_fix_height: int = 640,
    hires_fix_strength: float = 0.5,
    launch_wait: float = 60.0,
) -> str:
    _ensure_running(launch_wait=launch_wait)
    resp = requests.post(
        f"{BASE_URL}/sdapi/v1/txt2img",
        json={
            "prompt": "masterpiece, best quality, extremely detailed, intricate line art, "
            "professional anime illustration, flat cel shading, 2D anime style, sharp focus, " + prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "guidance_scale": guidance_scale,
            "sampler": sampler,
            "clip_skip": 2,
            "seed": -1,
            "batch_size": 1,
            "hires_fix": hires_fix,
            "hires_fix_width": hires_fix_width,
            "hires_fix_height": hires_fix_height,
            "hires_fix_strength": hires_fix_strength,
        },
        timeout=300,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"画像生成失敗 ({resp.status_code}): {resp.text}")
    images = resp.json().get("images", [])
    if not images:
        raise RuntimeError(f"完了したが画像データが空です: {resp.text[:300]}")
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(images[0]))
    return out_path


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "1girl, cute anime girl, bust-up portrait, masterpiece, best quality"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/draw_things_image.png"
    print(generate_image(prompt, out))
