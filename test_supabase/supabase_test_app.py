from urllib.parse import urlparse

import psycopg
import streamlit as st


st.set_page_config(page_title="Supabase connection test")
st.title("Supabase PostgreSQL connection test")

# Read the connection string from Streamlit secrets.
try:
    database_url = st.secrets["supabase"]["database_url"]
except Exception:
    st.error(
        "Connection settings were not found. "
        "Check .streamlit/secrets.toml."
    )
    st.stop()

# Show only the username to help diagnose connection settings.
parsed_url = urlparse(database_url)
st.write("接続ユーザー:", parsed_url.username)

if not parsed_url.username or not parsed_url.hostname:
    st.error("接続URLの形式を確認してください。")
    st.stop()

with st.form("test_entry_form"):
    message = st.text_input("Enter a test message")
    submitted = st.form_submit_button("Save")

if submitted:
    if not message.strip():
        st.warning("メッセージを入力してください。")
    else:
        try:
            with psycopg.connect(database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO public.streamlit_test_entries (message)
                        VALUES (%s)
                        """,
                        (message.strip(),),
                    )
            st.success("メッセージを保存しました。")
        except Exception as error:
            st.error(f"保存エラー: {type(error).__name__}: {error}")

st.subheader("Recently saved messages")

try:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, message, created_at
                FROM public.streamlit_test_entries
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            rows = cursor.fetchall()

    if rows:
        st.dataframe(
            [
                {"id": row[0], "message": row[1], "created_at": row[2]}
                for row in rows
            ],
            width="stretch",
        )
    else:
        st.info("保存されたメッセージはありません。")
except Exception as error:
    st.error(f"読み込みエラー: {type(error).__name__}: {error}")