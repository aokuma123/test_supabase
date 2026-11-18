import streamlit as st
import streamlit.components.v1 as components
import psycopg2
from psycopg2.extras import Json
import json
import re
import uuid

# ---------------------------------------------------------
# 0. ページ設定とサンプルJSONデータ（他担当者出力の想定形式）
# ---------------------------------------------------------
st.set_page_config(page_title="Rasch適性判定・作問支援ツール", layout="wide")

SAMPLE_JSON_DATA = [
    {
        "item_id": "JSON_001",
        "sentence": "This window was broken by the strong wind last night.",
        "target_phrase": "broken",
        "grammar_label": "受動態",
        "detected_grammars": ["受動態"],
        "reason": "be動詞(was) + 過去分詞(broken) + 行為者(by the strong wind)"
    },
    {
        "item_id": "JSON_002",
        "sentence": "The prestigious symposium which was organized by ubiquitous experts exacerbated the controversy.",
        "target_phrase": "which",
        "grammar_label": "関係節",
        "detected_grammars": ["関係節", "受動態"],
        "reason": "先行詞(symposium)を修飾する主格の関係代名詞"
    },
    {
        "item_id": "JSON_003",
        "sentence": "He read the book.",
        "target_phrase": "read",
        "grammar_label": "受動態（比較対象・能動態例）",
        "detected_grammars": ["受動態"],
        "reason": "動詞の過去形判定テスト"
    }
]

# 語彙ノイズ判定用の簡易チェックリスト（プロトタイプ用：難解・抽象語の例）
ADVANCED_WORDS_SAMPLE = {
    "prestigious", "symposium", "ubiquitous", "exacerbated",
    "controversy", "ambiguous", "subsequently", "deteriorate"
}

# ---------------------------------------------------------
# 1. 第1段階：英文・判定結果のRasch分析適性判定ロジック
# ---------------------------------------------------------
def evaluate_rasch_suitability(sentence: str, target_phrase: str, detected_grammars: list):
    """
    Rasch分析の前提（一次元性・語彙ノイズ排除・文脈手がかり）に基づき英文を診断する
    """
    issues = []
    suggestions = []

    words = re.findall(r"[A-Za-z']+", sentence)
    word_count = len(words)
    lower_words = [w.lower() for w in words]

    # チェック1：一文一論点（一次元性の担保）
    unique_grammars = list(set(detected_grammars))
    if len(unique_grammars) > 1:
        issues.append(f"【一文多論点】1文に複数の対象文法（{', '.join(unique_grammars)}）が含まれています。")
        suggestions.append("測定したい文法1つだけが残るように、不要な節や修飾構造を削って単文化してください。")

    # チェック2：語彙ノイズの有無（純粋な文法測定の担保）
    hard_words = [w for w in words if w.lower() in ADVANCED_WORDS_SAMPLE]
    if hard_words:
        issues.append(f"【語彙ノイズ】基礎水準を超える可能性のある語彙が含まれています: `{', '.join(hard_words)}`")
        suggestions.append("語彙力不足による誤答を防ぐため、中学・高校基礎レベルの平易な単語へ置き換えてください。")

    # チェック3：極端な文長（処理負荷の偏り）
    if word_count > 20:
        issues.append(f"【文長過多】語数が {word_count} 語と長く、読解負荷が難易度に影響する可能性があります。")
        suggestions.append("20語以内を目安に修飾語句を整理してください。")
    elif word_count < 5:
        issues.append(f"【文脈不足】語数が {word_count} 語と短すぎます。")
        suggestions.append("時制や態を一意に特定できる副詞句・前置詞句（例: last night, than ..., by ...）を補ってください。")

    # チェック4：文脈上の手がかり（空欄化後に正解を絞れる要素があるか）
    cue_words = {"by", "than", "yesterday", "last", "tomorrow", "since", "for", "who", "which", "whose"}
    has_cue = any(w in cue_words for w in lower_words)
    if not has_cue:
        issues.append("【手がかり不足】文中に時制・態・比較・先行詞を論理的に限定する手がかり語が見当たりません。")
        suggestions.append("空欄を作った際に正解が1つに定まるよう、時間表現や比較対象などの手がかりを追加してください。")

    is_suitable = len(issues) == 0
    meta_features = {
        "word_count": word_count,
        "grammar_count": len(unique_grammars),
        "hard_word_count": len(hard_words),
        "has_context_cue": has_cue
    }
    return is_suitable, issues, suggestions, meta_features

# ---------------------------------------------------------
# 2. 第2段階：選択肢作成後の一意性・形式チェック
# ---------------------------------------------------------
def validate_question_options(question_text: str, options: list, correct_answer: str):
    errors = []
    if "(      )" not in question_text and "____" not in question_text:
        errors.append("問題文に空欄（`(      )` または `____`）が含まれていません。")
    cleaned = [opt.strip() for opt in options if opt.strip()]
    if len(cleaned) != 4:
        errors.append("選択肢は4つすべて入力してください。")
    if len(set(o.lower() for o in cleaned)) != len(cleaned):
        errors.append("選択肢の中に重複（大文字・小文字違いを含む）があります。")
    if correct_answer not in cleaned:
        errors.append("正解が4つの選択肢の中に含まれていません。")
    return errors

# ---------------------------------------------------------
# 3. DB保存処理
# ---------------------------------------------------------
def save_question_to_db(record: dict):
    db_url = st.secrets["supabase"]["database_url"]
    conn = psycopg2.connect(db_url, sslmode="require")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.quiz_questions (
                        question_id, grammar_label, source_sentence, rewritten_sentence,
                        question_text, options, correct_answer, explanation,
                        suitability_status, is_rewritten, review_status, meta_features
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (question_id) DO UPDATE SET
                        grammar_label = EXCLUDED.grammar_label,
                        rewritten_sentence = EXCLUDED.rewritten_sentence,
                        question_text = EXCLUDED.question_text,
                        options = EXCLUDED.options,
                        correct_answer = EXCLUDED.correct_answer,
                        explanation = EXCLUDED.explanation,
                        suitability_status = EXCLUDED.suitability_status,
                        is_rewritten = EXCLUDED.is_rewritten,
                        review_status = EXCLUDED.review_status,
                        meta_features = EXCLUDED.meta_features;
                    """,
                    (
                        record["question_id"],
                        record["grammar_label"],
                        record["source_sentence"],
                        record["rewritten_sentence"],
                        record["question_text"],
                        Json(record["options"]),
                        record["correct_answer"],
                        record["explanation"],
                        record["suitability_status"],
                        record["is_rewritten"],
                        record["review_status"],
                        Json(record["meta_features"])
                    )
                )
    finally:
        conn.close()

# ---------------------------------------------------------
# 4. 状態管理（JSON選択変更時に画面トップへスクロール）
# ---------------------------------------------------------
if "scroll_to_top" not in st.session_state:
    st.session_state.scroll_to_top = False

def on_item_change():
    st.session_state.scroll_to_top = True

# --- サイドバー：作問対象選択（最上部）＋ JSON読込 ---
with st.sidebar:
    if "json_items" in st.session_state and st.session_state.json_items:
        st.header("1. 作問対象の英文を選択")
        items = st.session_state.json_items
        item_labels = [
            f"{it.get('item_id', idx)} | [{it.get('grammar_label', '不明')}] {it.get('sentence', '')}"
            for idx, it in enumerate(items)
        ]
        selected_idx = st.selectbox(
            "問題を選択（変更で画面上部へ移動）：",
            range(len(items)),
            format_func=lambda i: item_labels[i],
            key="selected_json_idx",
            on_change=on_item_change
        )
        st.divider()

    st.header("2. 文法判定JSONの読込")
    uploaded_file = st.file_uploader("判定結果JSONファイルをアップロード", type=["json"])

    if uploaded_file is not None:
        try:
            loaded = json.load(uploaded_file)
            st.session_state.json_items = loaded if isinstance(loaded, list) else [loaded]
            st.session_state.scroll_to_top = True
            st.success(f"{len(st.session_state.json_items)} 件のデータを読み込みました。")
        except Exception as e:
            st.error(f"JSON読込エラー: {e}")

    if st.button("サンプルJSONを読み込む（テスト用）", use_container_width=True):
        st.session_state.json_items = SAMPLE_JSON_DATA
        st.session_state.scroll_to_top = True
        st.rerun()

# 対象が変更された直後は画面の一番上へスクロールさせる
if st.session_state.scroll_to_top:
    st.session_state.scroll_to_top = False
    components.html(
        """
        <script>
            const mainSection = window.parent.document.querySelector('section.main');
            if (mainSection) {
                mainSection.scrollTo({top: 0, behavior: 'smooth'});
            }
            window.parent.scrollTo({top: 0, behavior: 'smooth'});
        </script>
        """,
        height=0
    )

# ---------------------------------------------------------
# 5. メインUI
# ---------------------------------------------------------
st.title("🛠️ Rasch分析適性判定・作問支援ツール（プロトタイプ）")
st.caption("JSON読込 → 第1段階：Rasch適性判定・リライト支援 → 第2段階：四択作成・一意性検証 → DB登録")

if "json_items" not in st.session_state or not st.session_state.json_items:
    st.info("👈 左のサイドバーから文法判定JSONをアップロードするか、「サンプルJSONを読み込む」を押してください。")
    st.stop()

items = st.session_state.json_items
selected_idx = st.session_state.get("selected_json_idx", 0)
current_item = items[selected_idx]

st.divider()

# =========================================================
# 第1段階：英文段階のRasch適性判定・修正支援
# =========================================================
st.header("🔍 第1段階：Rasch分析適性判定・修正支援")

st.markdown(f"- **対象文法ラベル：** `{current_item.get('grammar_label', '')}`")
st.markdown(f"- **検出された文法要素：** `{', '.join(current_item.get('detected_grammars', []))}`")
st.markdown(f"- **判定根拠：** {current_item.get('reason', '（記載なし）')}")

orig_sentence = current_item.get("sentence", "")
target_phrase = current_item.get("target_phrase", "")

st.text_area("元の入力英文（読み取り専用）", value=orig_sentence, height=75, disabled=True)

edited_sentence = st.text_area(
    "作問用英文（要修正の場合はここでリライトして再判定）",
    value=orig_sentence,
    height=80,
    key=f"edit_sent_{selected_idx}"
)

is_rewritten = (edited_sentence.strip() != orig_sentence.strip())

# リアルタイムで適性判定を実行
is_suitable, issues, suggestions, meta_features = evaluate_rasch_suitability(
    edited_sentence,
    target_phrase,
    current_item.get("detected_grammars", [current_item.get("grammar_label", "")])
)

if is_suitable:
    st.success("✅ **適性判定：OK（Rasch分析に適しています）**")
else:
    st.warning("⚠️ **適性判定：要修正（Rasch分析の前提を損なう恐れがあります）**")
    for iss, sug in zip(issues, suggestions):
        st.markdown(f"- {iss}\n  - 💡 **修正案：** {sug}")

with st.expander("抽出された英文特徴メタデータ（分析用）"):
    st.json(meta_features)

st.divider()

# =========================================================
# 第2段階：作問支援UI・選択肢作成・一意性検証
# =========================================================
st.header("✏️ 第2段階：作問支援UI・一意性検証")

if target_phrase and target_phrase in edited_sentence:
    template_q = edited_sentence.replace(target_phrase, "(      )", 1)
else:
    template_q = edited_sentence

question_text = st.text_area(
    "問題文の編集（空欄は `(      )` で表記）",
    value=template_q,
    height=80,
    key=f"q_text_{selected_idx}"
)

st.markdown("**四択の選択肢（1つ目を正解として入力し、出題時にシャッフルする想定）**")
c1, c2 = st.columns(2)
with c1:
    opt_correct = st.text_input("選択肢1（★正解）", value=target_phrase, key=f"opt1_{selected_idx}")
    opt_d2 = st.text_input("選択肢3（誤答肢2）", value="", key=f"opt3_{selected_idx}")
with c2:
    opt_d1 = st.text_input("選択肢2（誤答肢1）", value="", key=f"opt2_{selected_idx}")
    opt_d3 = st.text_input("選択肢4（誤答肢3）", value="", key=f"opt4_{selected_idx}")

st.info("ℹ️ **一意性確認**：作成した4つの選択肢の中で、文脈上正解が1つだけに論理的に決まることを確認してから保存してください。")

q_id = st.text_input("登録用問題ID", value=f"Q_{current_item.get('item_id', uuid.uuid4().hex[:4])}", key=f"qid_{selected_idx}")

if st.button("検証してSupabaseに「確認済み」として保存", type="primary", use_container_width=True):
    options_list = [opt_correct, opt_d1, opt_d2, opt_d3]
    val_errors = validate_question_options(question_text, options_list, opt_correct)

    if not is_suitable:
        st.error("第1段階の「Rasch分析適性判定」が要修正のままです。上の英文を修正して適性OKにしてから保存してください。")
    elif val_errors:
        for err in val_errors:
            st.error(f"入力エラー：{err}")
    else:
        record = {
            "question_id": q_id.strip(),
            "grammar_label": current_item.get("grammar_label", ""),
            "source_sentence": orig_sentence,
            "rewritten_sentence": edited_sentence,
            "question_text": question_text.strip(),
            "options": [o.strip() for o in options_list],
            "correct_answer": opt_correct.strip(),
            "explanation": "",
            "suitability_status": "suitable",
            "is_rewritten": is_rewritten,
            "review_status": "confirmed",
            "meta_features": meta_features
        }
        try:
            save_question_to_db(record)
            st.success(f"🎉 問題 `{q_id}` を確認済み問題としてSupabaseに保存しました！")
        except Exception as e:
            st.error(f"DB保存エラー: {e}")