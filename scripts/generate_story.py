"""Geminiで「電車男」風の一人称フィクションストーリー(全5話の連載)を生成する。"""
from __future__ import annotations

import json
import os
import random
import sys
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MODEL = "gemini-flash-latest"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

TOTAL_EPISODES = 5

SYSTEM_PROMPT = """あなたはブログ記事のフィクション連載ライターです。
「電車男」のような、2ch/5chまとめ的なノリの一人称体験談風フィクションを、全5話の連載として書いてください。

要件:
- 完全な作り話(フィクション)。実在の人物・団体を実名で登場させない。
- 文体はカジュアルな口語体、自虐や照れ隠しのユーモアを交える。
- 各話の冒頭1〜2文で「おっ」と思わせる引きを作る。
- 主人公はライブ参戦・推し活・参戦グッズ文化(缶バッジ、痛バッグ、参戦服、ラバーストラップ、ラミネートカードなど)が好きな設定。実在アーティスト名は出さず、架空のバンド名/アーティスト名を使う。
- ストーリー全体のオチは指定されたパターンに従い、恋愛オチに偏らないこと。
- 最終話(5話目)以外は話の途中で終わり、次回が気になる引きで締めること。最終話はきちんと完結させる。
- 本文は各話600〜1000文字程度。
- slugは記事内容を表す英語小文字ケバブケース(3〜5語)。シリーズ全体を表すもの(話数は含めない)。
- episode_summaryは「次の話を書くAI」への引き継ぎメモ。これまでの話の展開も踏まえ、登場人物・関係性・未解決の伏線を3〜4文で累積的にまとめる。
- protagonist_name, band_nameは主人公の呼び名(あだ名でよい)と架空バンド名。第1話で決めたら以降の話でも同じ値をそのまま返すこと。
- 出力は必ず次のJSON形式のみで返す。他の文章やコードブロック記法(```)は一切付けない:
{"title": "各話のタイトル(20文字前後、話数表記は含めない)", "slug": "english-kebab-case-slug", "body": "本文全体(改行は\\nで表現)", "episode_summary": "次話への引き継ぎ要約", "protagonist_name": "主人公の呼び名", "band_name": "架空バンド名"}
"""

STORY_PATTERNS = [
    ("恋愛・運命の出会い系", "会場で出会った相手にときめく展開(頻度は控えめに)"),
    ("同担/戦友との友情系", "性別問わず、同じ推しを応援する者同士が意気投合する友情オチ"),
    ("ほのぼの家族・世代系", "家族(親・子・祖父母など)や職場の先輩後輩が推し活を通じて心温まる交流をするオチ"),
    ("爆笑失敗からの逆転系", "大失敗するが誰かの機転や自分の工夫で笑って終わるオチ(恋愛要素なし)"),
    ("感動のライブ体験系", "新しい人物との出会いより、ライブそのものの感動・自分の成長にフォーカスするオチ"),
    ("ご近所・職場の意外な共通点系", "身近な人(隣人・同僚・店員など)と推し活が意外に繋がる、ほっこり系のオチ(恋愛要素なし)"),
]


def _build_user_prompt(theme: str, episode: int, is_final: bool, pattern_name: str, pattern_desc: str, state: dict | None) -> str:
    base = f"今回のお題・方向性: {theme}" if theme else "今回のお題: 自由に面白い話を考えてください。"

    if episode == 1:
        return (
            f"{base}\n"
            f"全{TOTAL_EPISODES}話シリーズの第1話です。\n"
            f"今回使うオチのパターン(5話通してこの方向性に向かう): 【{pattern_name}】{pattern_desc}\n"
            "主人公の呼び名・架空バンド名は自由に決めてください。"
        )

    final_note = "今回が最終話です。きちんと完結させてください。" if is_final else "話を進め、次回が気になる引きで締めてください。"
    return (
        f"全{TOTAL_EPISODES}話シリーズの第{episode}話です。{final_note}\n"
        f"主人公: {state['protagonist_name']} / 架空バンド: {state['band_name']}\n"
        f"これまでのあらすじ: {state['summary_so_far']}\n"
        f"オチのパターン(この方向性で進めること): 【{pattern_name}】{pattern_desc}"
    )


def generate_story(theme: str = "", state: dict | None = None, retries: int = 4) -> dict:
    """state が None なら新規シリーズの第1話、指定があれば続きの話を生成する。

    戻り値には LLM の出力に加えて episode/total_episodes/is_final/pattern_name/pattern_desc も含む。
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(".env に GEMINI_API_KEY が未設定です")

    if state is None:
        episode = 1
        pattern_name, pattern_desc = random.choice(STORY_PATTERNS)
    else:
        episode = state["episode"]
        pattern_name, pattern_desc = state["pattern_name"], state["pattern_desc"]

    is_final = episode >= TOTAL_EPISODES
    user_prompt = _build_user_prompt(theme, episode, is_final, pattern_name, pattern_desc, state)

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
            required = ("title", "slug", "body", "episode_summary", "protagonist_name", "band_name")
            if not all(k in story for k in required):
                last_error = RuntimeError(f"必須キー欠落: {list(story)}")
                continue
            story["episode"] = episode
            story["total_episodes"] = TOTAL_EPISODES
            story["is_final"] = is_final
            story["pattern_name"] = pattern_name
            story["pattern_desc"] = pattern_desc
            return story
        except json.JSONDecodeError as e:
            last_error = e
            continue

    raise last_error


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else ""
    result = generate_story(theme)
    print(json.dumps(result, ensure_ascii=False, indent=2))
