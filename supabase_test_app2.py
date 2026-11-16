import streamlit as st
import psycopg2
import uuid

# ---------------------------------------------------------
# 1. テスト用問題データ（全3問・四択穴埋め）
# ---------------------------------------------------------
QUESTIONS = [
    {
        "id": "Q1",
        "grammar": "受動態",
        "sentence": "This window was (      ) by the strong wind last night.",
        "options": ["break", "broke", "broken", "breaking"],
        "answer": "broken"
    },
    {
        "id": "Q2",
        "grammar": "関係代名詞",
        "sentence": "The girl (      ) is playing the piano over there is my sister.",
        "options": ["who", "which", "whom", "whose"],
        "answer": "who"
    },
    {
        "id": "Q3",
        "grammar": "比較級",
        "sentence": "Tokyo is much (      ) than my hometown.",
        "options": ["large", "larger", "largest", "more large"],
        "answer": "larger"
    }
]

# ---------------------------------------------------------
# 2. DB保存処理
# ---------------------------------------------------------
def save_responses_to_supabase(session_id: str, answers: dict):
    conn = psycopg2.connect(
        host=st.secrets["SUPABASE_DB_HOST"],
        port=int(st.secrets.get("SUPABASE_DB_PORT", 5432)),
        dbname=st.secrets.get("SUPABASE_DB_NAME", "postgres"),
        user=st.secrets["SUPABASE_DB_USER"],
        password=st.secrets["SUPABASE_DB_PASSWORD"],
        sslmode="require"
    )
    try:
        with conn:
            with conn.cursor() as cur:
                for q in QUESTIONS:
                    q_id = q["id"]
                    selected = answers[q_id]
                    is_correct = 1 if selected == q["answer"] else 0
                    cur.execute(
                        """
                        INSERT INTO public.test_streamlit_quiz_responses
                            (session_id, question_id, selected_option, is_correct)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (session_id, question_id) DO NOTHING;
                        """,
                        (session_id, q_id, selected, is_correct)
                    )
    finally:
        conn.close()

# ---------------------------------------------------------
# 3. セッション状態の初期化
# ---------------------------------------------------------
if "started" not in st.session_state:
    st.session_state.started = False
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}  # { "Q1": "broken", ... }
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "session_id" not in st.session_state:
    st.session_state.session_id = f"TEST_{uuid.uuid4().hex[:6].upper()}"

def reset_quiz():
    st.session_state.started = False
    st.session_state.current_idx = 0
    st.session_state.answers = {}
    st.session_state.submitted = False
    st.session_state.session_id = f"TEST_{uuid.uuid4().hex[:6].upper()}"

# ---------------------------------------------------------
# 4. 画面表示（UI）
# ---------------------------------------------------------
st.title("英文法クイズ 動作テスト（全3問）")

# 【画面1】スタート前
if not st.session_state.started:
    st.write("全3問の英文穴埋め四択問題です。すべての問題に回答すると送信ボタンが表示されます。")
    # テスト用に参加者IDを手動変更できるようにしておく（複数人分のダミー回答作成に便利）
    st.session_state.session_id = st.text_input(
        "参加者コード（テスト用ID）", value=st.session_state.session_id
    )
    if st.button("スタート", type="primary"):
        st.session_state.started = True
        st.rerun()

# 【画面3】送信完了後
elif st.session_state.submitted:
    st.success(f"回答をSupabaseに保存しました！（参加者コード: {st.session_state.session_id}）")
    st.subheader("回答結果と正解")
    for q in QUESTIONS:
        user_ans = st.session_state.answers.get(q["id"])
        correct_ans = q["answer"]
        mark = "✅ 正解" if user_ans == correct_ans else "❌ 不正解"
        st.write(f"**{q['id']}** ({q['grammar']}): {mark} ｜ あなたの回答: `{user_ans}` / 正解: `{correct_ans}`")
    
    st.divider()
    if st.button("別の参加者としてもう一度テストする"):
        reset_quiz()
        st.rerun()

# 【画面2】クイズ回答中
else:
    idx = st.session_state.current_idx
    total = len(QUESTIONS)
    q = QUESTIONS[idx]

    st.caption(f"参加者コード: {st.session_state.session_id} ｜ 進捗: {idx + 1} / {total} 問目")
    st.progress((idx + 1) / total)

    st.subheader(f"第 {idx + 1} 問")
    st.markdown(f"### {q['sentence']}")

    # すでに回答済みの場合はその選択肢を初期選択状態にする
    saved_choice = st.session_state.answers.get(q["id"], None)
    default_index = q["options"].index(saved_choice) if saved_choice in q["options"] else None

    choice = st.radio(
        "空欄に入る最も適切な語を1つ選んでください：",
        options=q["options"],
        index=default_index,
        key=f"radio_{q['id']}"
    )

    # 選択されたら即座に session_state に保存
    if choice is not None:
        st.session_state.answers[q["id"]] = choice

    st.write("")  # 余白

    # ナビゲーションボタン（戻る / 次へ）
    col_prev, col_space, col_next = st.columns([1, 2, 1])

    with col_prev:
        # 最初の問題（idx == 0）では表示しない
        if idx > 0:
            if st.button("← 戻る", use_container_width=True):
                st.session_state.current_idx -= 1
                st.rerun()

    with col_next:
        # 最後の問題（idx == total - 1）では表示しない
        if idx < total - 1:
            if st.button("次へ →", use_container_width=True):
                st.session_state.current_idx += 1
                st.rerun()

    st.divider()

    # すべての問題（3問すべて）に回答済みの場合のみ送信ボタンを表示
    all_answered = len(st.session_state.answers) == total
    if all_answered:
        if st.button("回答を送信", type="primary", use_container_width=True):
            try:
                save_responses_to_supabase(st.session_state.session_id, st.session_state.answers)
                st.session_state.submitted = True
                st.rerun()
            except Exception as e:
                st.error(f"DB保存中にエラーが発生しました: {e}")
    else:
        unanswered_count = total - len(st.session_state.answers)
        st.info(f"未回答の問題が {unanswered_count} 問あります。すべて回答すると送信ボタンが表示されます。")