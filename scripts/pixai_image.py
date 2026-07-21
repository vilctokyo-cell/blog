"""PixAI API で画像を1枚生成する。

事前準備: .env に PIXAI_API_KEY を設定すること(api@withpixai.artへのAPI申請が承認され次第)。
モデルはデフォルトで Tsubaki.2(手足のアナトミー精度が高いとPixAI公式が明記)を使う。
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.pixai.art/v2"
TASK_URL = "https://api.pixai.art/v1/task"

# 推奨モデル(platform.pixai.art/en/docs/references/models より)
MODEL_TSUBAKI_2 = "1983308862240288769"  # 手足のアナトミー精度が高い・プロンプト理解力が高い(デフォルト)
MODEL_HARUKA_V2 = "1861558740588989558"  # 手の描写が安定
MODEL_HOSHINO_V2 = "1954632828118619567"  # 日本で人気のスタイル

DEFAULT_MODEL = MODEL_TSUBAKI_2


def _headers():
    api_key = os.environ.get("PIXAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env に PIXAI_API_KEY が未設定です")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def generate_image(prompt: str, out_path: str, model_id: str = DEFAULT_MODEL, aspect_ratio: str = "1:1") -> str:
    resp = requests.post(
        f"{BASE_URL}/image/create",
        headers=_headers(),
        json={"modelVersionId": model_id, "prompt": prompt, "aspectRatio": aspect_ratio, "mode": "standard"},
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"タスク作成失敗 ({resp.status_code}): {resp.text}")
    task_id = resp.json()["id"]

    for _ in range(60):
        time.sleep(2)
        poll = requests.get(f"{TASK_URL}/{task_id}", headers=_headers(), timeout=30)
        poll.raise_for_status()
        data = poll.json()
        status = data.get("status")
        if status == "completed":
            urls = data.get("outputs", {}).get("mediaUrls", [])
            if not urls:
                raise RuntimeError(f"完了したが画像URLが空です: {data}")
            img = requests.get(urls[0], timeout=60)
            img.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(img.content)
            return out_path
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"画像生成失敗 (status={status}): {data}")
    raise RuntimeError("タイムアウト: 120秒以内に完了しませんでした")


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "1girl, cute handmade sticker style, masterpiece, best quality"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/pixai_image.png"
    print(generate_image(prompt, out))
