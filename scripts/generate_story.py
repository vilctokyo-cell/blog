"""Geminiで「電車男」風の一人称フィクションストーリー(タイトル+スラッグ+本文)を生成する。"""
import json
import os
import random
import sys
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MODEL = "gemini-flash-latest"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

SYSTEM_PROMPT = """あなたはブログ記事のフィクションストーリーライターです。
「電車男」のような、2ch/5chまとめ的なノリの一人称体験談風フィクションを書いてください。

要件:
- 完全な作り話(フィクション)。実在の人物・団体を実名で登場させない。
- 文体はカジュアルな口語体、自虐や照れ隠しのユーモアを交える。
- 冒頭1〜2文で「おっ」と思わせる引きを作る(結論の匂わせ、意外な出来事の予告など)。
- 主人公はライブ参戦・推し活・参戦グッズ文化(缶バッジ、痛バッグ、参戦服、ラバーストラップ、ラミネートカードなど)が好きな設定にしてよい。実在アーティスト名は出さない(架空のバンド名/アーティスト名にする)。
- 読者が続きを読みたくなる、共感・驚き・ほっこりのどれかで締める。
- 恋愛オチに偏らないこと。今回指定されたオチのパターンに従うこと。
- 本文は800〜1400文字程度。
- slugは記事内容を表す英語小文字ケバブケース(3〜5語)。
- 出力は必ず次のJSON形式のみで返す。他の文章やコードブロック記法(```)は一切付けない:
{"title": "記事タイトル(20文字前後)", "slug": "english-kebab-case-slug", "body": "本文全体(改行は\\nで表現)"}
"""

STORY_PATTERNS = [
    ("恋愛・運命の出会い系", "会場で出会った相手にときめく展開(頻度は控えめに)"),
    ("同担/戦友との友情系", "性別問わず、同じ推しを応援する者同士が意気投合する友情オチ"),
    ("ほのぼの家族・世代系", "家族(親・子・祖父母など)や職場の先輩後輩が推し活を通じて心温まる交流をするオチ"),
    ("爆笑失敗からの逆転系", "大失敗するが誰かの機転や自分の工夫で笑って終わるオチ(恋愛要素なし)"),
    ("感動のライブ体験系", "新しい人物との出会いより、ライブそのものの感動・自分の成長にフォーカスするオチ"),
    ("ご近所・職場の意外な共通点系", "身近な人(隣人・同僚・店員など)と推し活が意外に繋がる、ほっこり系のオチ(恋愛要素なし)"),
]


def generate_story(theme: str = "", retries: int = 4) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(".env に GEMINI_API_KEY が未設定です")

    pattern_name, pattern_desc = random.choice(STORY_PATTERNS)
    base = f"今回のお題・方向性: {theme}" if theme else "今回のお題: 自由に面白い話を考えてください。"
    user_prompt = f"{base}\n今回使うオチのパターン: 【{pattern_name}】{pattern_desc}"

    last_error = None
    for _ in range(retries):
        resp = requests.post(
            API_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": user_prompt}]}],
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 4096,
                    "thinkingConfig": {"thinkingBudget": 512},
                },
            },
        )
        if resp.status_code >= 300:
            last_error = RuntimeError(f"生成失敗 ({resp.status_code}): {resp.text}")
            continue

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            finish_reason = data.get("candidates", [{}])[0].get("finishReason", "unknown")
            last_error = RuntimeError(f"生成失敗 (finishReason={finish_reason}): {data}")
            continue
        try:
            story = json.loads(text, strict=False)
            if not all(k in story for k in ("title", "slug", "body")):
                last_error = RuntimeError(f"必須キー欠落: {list(story)}")
                continue
            return story
        except json.JSONDecodeError as e:
            last_error = e
            continue

    raise last_error


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else ""
    result = generate_story(theme)
    print(json.dumps(result, ensure_ascii=False, indent=2))
