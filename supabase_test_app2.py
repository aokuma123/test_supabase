import streamlit as st
import psycopg2
import uuid
import time
import math

# ---------------------------------------------------------
# 0. 定数設定
# ---------------------------------------------------------
TIME_LIMIT_SECONDS = 120  # テスト用制限時間：2分（120秒）

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
# 2. DB保存処理（未回答・タイムアップも区別して保存）
# ---------------------------------------------------------
def save_responses_to_supabase(session_id: str, answers: dict, is_timeout: bool = False):
    db_url = st.secrets["supabase"]["database_url"]
    conn = psycopg2.connect(db_url, sslmode="require")
    try:
        with conn:
            with conn.cursor() as cur:
                for q in QUESTIONS:
                    q_id = q["id"]
                    selected = answers.get(q_id)  # 未回答なら None

                    if selected is not None:
                        status = "answered"
                        is_correct = 1 if selected == q["answer"] else 0
                    else:
                        # 未回答は誤答(0)ではなく NULL（欠測）として記録
                        status = "unanswered_timeout" if is_timeout else "unanswered"
                        is_correct = None

                    cur.execute(
                        """
                        INSERT INTO public.test_streamlit_quiz_responses
                            (session_id, question_id, selected_option, response_status, is_correct)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (session_id, question_id) DO NOTHING;
                        """,
                        (session_id, q_id, selected, status, is_correct)
                    )
    finally:
        conn.close()

# ---------------------------------------------------------
# 3. セッション状態の初期化
# ---------------------------------------------------------
if "started" not in st.session_state:
    st.session_state.started = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "time_up" not in st.session_state:
    st.session_state.time_up = False
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "session_id" not in st.session_state:
    st.session_state.session_id = f"TEST_{uuid.uuid4().hex[:6].upper()}"

def reset_quiz():
    st.session_state.started = False
    st.session_state.start_time = None
    st.session_state.time_up = False
    st.session_state.current_idx = 0
    st.session_state.answers = {}
    st.session_state.submitted = False
    st.session_state.session_id = f"TEST_{uuid.uuid4().hex[:6].upper()}"

# ---------------------------------------------------------
# 4. タイマー表示（1分以上は分単位、1分未満は毎秒カウントダウン）
# ---------------------------------------------------------
@st.fragment(run_every=1)
def render_timer():
    if st.session_state.start_time is None:
        return

    elapsed = time.time() - st.session_state.start_time
    remaining = max(0, int(math.ceil(TIME_LIMIT_SECONDS - elapsed)))

    # タイムアップ判定
    if remaining <= 0 and not st.session_state.time_up:
        st.session_state.time_up = True
        st.rerun()

    # 残り1分（60秒）未満になったら警告表示＋毎秒カウントダウン
    if remaining < 60:
        st.warning(f"⚠️ 残り時間が少なくなっています：残り **{remaining} 秒**")
    else:
        # 60秒以上のときは分単位（切り上げ）で表示（120〜61秒 → 2分、60秒 → 1分）
        remaining_mins = math.ceil(remaining / 60)
        st.info(f"⏱️ 残り時間：**約 {remaining_mins} 分**")

# ---------------------------------------------------------
# 5. 画面表示（UI）
# ---------------------------------------------------------
limit_mins = TIME_LIMIT_SECONDS // 60
st.title(f"英文法クイズ 動作テスト（制限時間{limit_mins}分）")

# 【画面1】スタート前
if not st.session_state.started:
    st.write(f"全3問の英文穴埋め四択問題です。制限時間は **{limit_mins}分** です。")
    st.session_state.session_id = st.text_input(
        "参加者コード（テスト用ID）", value=st.session_state.session_id
    )
    if st.button("スタート", type="primary"):
        st.session_state.started = True
        st.session_state.start_time = time.time()
        st.rerun()

# 【画面4】送信完了後
elif st.session_state.submitted:
    st.success(f"回答をSupabaseに保存しました！（参加者コード: {st.session_state.session_id}）")
    st.subheader("回答結果と正解")
    for q in QUESTIONS:
        user_ans = st.session_state.answers.get(q["id"])
        correct_ans = q["answer"]
        if user_ans is None:
            mark = "⚪ 未回答（欠測扱い）"
            disp_ans = "未回答"
        elif user_ans == correct_ans:
            mark = "✅ 正解"
            disp_ans = user_ans
        else:
            mark = "❌ 不正解"
            disp_ans = user_ans
        st.write(f"**{q['id']}** ({q['grammar']}): {mark} ｜ あなたの回答: `{disp_ans}` / 正解: `{correct_ans}`")

    st.divider()
    if st.button("別の参加者としてもう一度テストする"):
        reset_quiz()
        st.rerun()

# 【画面3】タイムアップ時（制限時間経過後：問題を閉じて送信ボタンのみ表示）
elif st.session_state.time_up:
    st.error("⏰ 制限時間が経過したため、回答を終了しました。")
    answered_count = len(st.session_state.answers)
    st.write(f"回答済み: **{answered_count} / {len(QUESTIONS)} 問**（未回答の問題は欠測データとして記録されます）")
    st.write("下のボタンを押して、ここまでの回答データを送信してください。")

    if st.button("回答を送信", type="primary", use_container_width=True):
        try:
            save_responses_to_supabase(
                st.session_state.session_id,
                st.session_state.answers,
                is_timeout=True
            )
            st.session_state.submitted = True
            st.rerun()
        except Exception as e:
            st.error(f"DB保存中にエラーが発生しました: {e}")

# 【画面2】クイズ回答中（制限時間内）
else:
    # 上部にタイマーを表示
    render_timer()

    idx = st.session_state.current_idx
    total = len(QUESTIONS)
    q = QUESTIONS[idx]

    st.caption(f"参加者コード: {st.session_state.session_id} ｜ 問題進捗: **{idx + 1} / {total} 問目**")

    st.subheader(f"第 {idx + 1} 問")
    st.markdown(f"### {q['sentence']}")

    saved_choice = st.session_state.answers.get(q["id"], None)
    default_index = q["options"].index(saved_choice) if saved_choice in q["options"] else None

    choice = st.radio(
        "空欄に入る最も適切な語を1つ選んでください：",
        options=q["options"],
        index=default_index,
        key=f"radio_{q['id']}"
    )

    if choice is not None:
        st.session_state.answers[q["id"]] = choice

    st.write("")

    col_prev, col_space, col_next = st.columns([1, 2, 1])

    with col_prev:
        if idx > 0:
            if st.button("← 戻る", use_container_width=True):
                st.session_state.current_idx -= 1
                st.rerun()

    with col_next:
        if idx < total - 1:
            if st.button("次へ →", use_container_width=True):
                st.session_state.current_idx += 1
                st.rerun()

    st.divider()

    # 時間内に全問回答し終わった場合も送信ボタンを表示
    all_answered = len(st.session_state.answers) == total
    if all_answered:
        if st.button("回答を送信", type="primary", use_container_width=True):
            try:
                save_responses_to_supabase(
                    st.session_state.session_id,
                    st.session_state.answers,
                    is_timeout=False
                )
                st.session_state.submitted = True
                st.rerun()
            except Exception as e:
                st.error(f"DB保存中にエラーが発生しました: {e}")
    else:
        unanswered_count = total - len(st.session_state.answers)
        st.info(f"未回答の問題が {unanswered_count} 問あります。すべて回答するか、制限時間が経過すると送信ボタンが表示されます。")