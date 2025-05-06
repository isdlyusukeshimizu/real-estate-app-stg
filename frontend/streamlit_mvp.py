import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import streamlit as st
import shutil
import pandas as pd
from io import StringIO
import json
import sqlite3
from datetime import datetime, timedelta, timezone
import hashlib
import bcrypt
import re
import jwt

JST = timezone(timedelta(hours=9))  # 日本時間のタイムゾーン

# Secrets／環境変数から得たパス文字列
raw_csv_path = st.secrets["KEN_ALL_CSV_PATH"]

# 相対パスならルート直下からの絶対パスに変換
if not os.path.isabs(raw_csv_path):
    KEN_ALL_CSV_PATH = os.path.join(ROOT, raw_csv_path)
else:
    KEN_ALL_CSV_PATH = raw_csv_path

# スクリプト内部でも os.getenv で拾えるように
os.environ["KEN_ALL_CSV_PATH"] = KEN_ALL_CSV_PATH

# Streamlit Cloud では st.secrets から取得
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")

# Secrets から GCP サービスアカウント情報を取得し、JSON文字列化して環境変数へ
sa_info = st.secrets["gcp_service_account"]
# AttrDict を通常の dict に変換してから JSON に
os.environ["GCP_SA_INFO_JSON"] = json.dumps(dict(sa_info))

# --- 定数 ---
SECRET_KEY = st.secrets.get("JWT_SECRET_KEY")
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_MINUTES = 60

# カスタムモジュールのインポート
from scripts.extract_info_from_pdf import ocr_pdf, extract_registry_office
from scripts.auto_mode_chatgpt import run_auto_mode
from scripts.pipeline import extract_owner_info
from scripts.concat_markitdown_extract_zipcode import get_zipcode
from scripts.merge_data import merge_data

# --- データベース初期化 ---
def init_db():
    conn = sqlite3.connect('data.db', check_same_thread=False)
    c = conn.cursor()
    # ユーザーテーブル：パスワードは SHA256 ハッシュを保存
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            role TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            registry_office TEXT,
            status TEXT,
            assigned_to TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            description TEXT,
            amount REAL
        )
    ''')
    conn.commit()
    return conn

conn = init_db()

# --- 入力バリデーション ---
def validate_email(email: str) -> bool:
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None

# --- 認証ヘルパー ---
def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())


def verify_password(password: str, pw_hash: bytes) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), pw_hash)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(JST) + expires_delta  # 日本時間で現在時刻＋有効期限
    else:
        expire = datetime.now(JST) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def register_user(name: str, email: str, password: str) -> tuple[bool, str]:
    if not name.strip():
        return False, "氏名を入力してください。"
    if not validate_email(email):
        return False, "有効なメールアドレスを入力してください。"
    if len(password) < 6:
        return False, "パスワードは6文字以上で設定してください。"
    c = conn.cursor()
    try:
        pw_hash = hash_password(password)
        c.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name.strip(), email.strip(), pw_hash, 'member')
        )
        conn.commit()
        return True, "登録が完了しました。ログインしてください。"
    except sqlite3.IntegrityError:
        return False, "このメールアドレスは既に登録されています。"


def authenticate_user(email: str, password: str) -> tuple[str | None, str | None]:
    c = conn.cursor()
    c.execute("SELECT id, name, password_hash, role FROM users WHERE email=?", (email.strip(),))
    row = c.fetchone()
    if row and verify_password(password, row[2]):
        user_id, name, _, role = row
        token = create_access_token({"user_id": user_id, "email": email, "role": role})
        return token, name
    return None, None

# --- セッション管理 ---
if 'token' not in st.session_state:
    st.session_state['token'] = None
if 'user_name' not in st.session_state:
    st.session_state['user_name'] = None
if 'role' not in st.session_state:
    st.session_state['role'] = None
if 'user' not in st.session_state:
    st.session_state['user'] = None




# --- アプリ起動 ---
st.set_page_config(page_title="不動産相続情報取得システム", layout="wide")
st.title("不動産相続情報システム")
st.text(f"土日祝日は18時～翌朝8時30分、平日は23時～翌朝8時30分、年末年始は終日(12/29～1/3)の時間は本システムの利用が出来ません。")
if 'user' not in st.session_state:
    st.session_state['user'] = None
    st.session_state['role'] = None

# --- 認証ページ ---
def login_page():
    st.title("ログイン")
    with st.form("login_form"):
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
    if submitted:
        token, name = authenticate_user(email, password)
        if token:
            st.session_state['token'] = token
            st.session_state['user_name'] = name
            st.session_state['user'] = name
            payload = decode_access_token(token)
            st.session_state['role'] = payload.get('role')
            st.success(f"ようこそ、{name} さん！")
            st.rerun()
        else:
            st.error("メールアドレスまたはパスワードが正しくありません。")


def signup_page():
    st.title("新規登録")
    with st.form("signup_form"):
        name = st.text_input("氏名")
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")
        password2 = st.text_input("パスワード（確認）", type="password")
        submitted = st.form_submit_button("登録")
    if submitted:
        if password != password2:
            st.error("パスワードが一致しません。再度確認してください。")
        elif register_user(name, email, password):
            st.success("登録が完了しました。ログインしてください。")
        else:
            st.error("このメールアドレスはすでに登録されています。")

# --- ログアウト ---
def logout():
    st.session_state.clear()
    st.rerun()

# --- ダッシュボード ---
def dashboard_page():
    st.title("ダッシュボード")
    # 月別リスト件数
    df = pd.read_sql_query(
        "SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS count FROM lists GROUP BY month", conn)
    if not df.empty:
        df = df.rename(columns={'month':'年月', 'count':'件数'}).set_index('年月')
        st.bar_chart(df)
    else:
        st.info("まだ取得リストがありません。")

# --- 取得リスト管理 ---
def list_management_page():
    st.title("取得リスト管理")
    uploaded = st.file_uploader("受付台帳 PDF をアップロード", type='pdf')
    if uploaded:
        if st.button("パイプライン実行 → CSV生成 & リスト登録"):
            with st.spinner("処理中... 少々お待ちください..."):
                # 保存
                os.makedirs('uploads', exist_ok=True)
                pdf_path = os.path.join('uploads', 'uploaded_ledger.pdf')
                with open(pdf_path, 'wb') as f:
                    f.write(uploaded.getbuffer())
                # パイプライン
                text = ocr_pdf(pdf_path)
                registry_office = extract_registry_office(text)
                pdf_paths = run_auto_mode(pdf_path, save_dir='downloads')
                df_owner = extract_owner_info(pdf_paths)
                # 郵便番号
                zip_records = []
                for addr in df_owner['所有者住所'].unique():
                    zip_records.append({'所有者住所':addr, '郵便番号':get_zipcode(addr)})
                df_zip = pd.DataFrame(zip_records)
                # CSV出力
                csv_path = os.path.join('uploads', 'final_output.csv')
                df_owner.to_csv('uploads/owner.csv', index=False, encoding='utf-8-sig')
                df_zip.to_csv('uploads/zip.csv', index=False, encoding='utf-8-sig')
                merge_data('uploads/owner.csv','uploads/zip.csv', csv_path, registry_office)
                st.success("最終 CSV が生成されました。")
                with open(csv_path, 'rb') as f:
                    st.download_button("CSVダウンロード", data=f, file_name='output.csv')
                # DB登録
                now = datetime.now().isoformat()
                c=conn.cursor()
                c.execute("INSERT INTO lists (created_at, registry_office, status, assigned_to) VALUES (?,?,?,?)", 
                          (now, registry_office, '未アタック', st.session_state['user']))
                conn.commit()
                st.success("取得リストに登録しました。")
    # 一覧
    st.subheader("一覧")
    df_list = pd.read_sql_query("SELECT * FROM lists", conn)
    if not df_list.empty:
        for i,row in df_list.iterrows():
            cols = st.columns([1,2,2,2,2])
            cols[0].write(row['id'])
            cols[1].write(row['created_at'])
            cols[2].selectbox("ステータス", ['未アタック','アタック済み','アポ獲得','成約','失注'], index=['未アタック','アタック済み','アポ獲得','成約','失注'].index(row['status']), key=f"status_{row['id']}", on_change=lambda rid=row['id']: update_list_status(rid))
            cols[3].text_input("担当者", value=row['assigned_to'], key=f"assignee_{row['id']}", on_change=lambda rid=row['id']: update_list_assignee(rid))
    else:
        st.info("登録済みの取得リストがありません。")

# ステータス更新

def update_list_status(rid):
    new_status = st.session_state[f"status_{rid}"]
    conn.execute("UPDATE lists SET status=? WHERE id=?", (new_status, rid))
    conn.commit()

# 担当者更新

def update_list_assignee(rid):
    new_assignee = st.session_state[f"assignee_{rid}"]
    conn.execute("UPDATE lists SET assigned_to=? WHERE id=?", (new_assignee, rid))
    conn.commit()

# --- 請求管理 ---
def billing_page():
    st.title("請求管理")
    df_billing = pd.read_sql_query("SELECT * FROM billing", conn)
    if not df_billing.empty:
        st.dataframe(df_billing)
    with st.form("billing_form"):
        desc = st.text_input("請求内容")
        amt = st.number_input("金額", min_value=0.0, format="%.2f")
        submitted = st.form_submit_button("請求作成")
    if submitted:
        now = datetime.now().isoformat()
        conn.execute("INSERT INTO billing (created_at, description, amount) VALUES (?,?,?)", (now, desc, amt))
        conn.commit()
        st.success("請求を登録しました。")
        st.rerun()

# --- メンバー管理 ---
def member_page():
    st.title("メンバー管理")
    df_users = pd.read_sql_query("SELECT * FROM users", conn)
    for i,row in df_users.iterrows():
        cols = st.columns([3,2])
        cols[0].write(row['email'])
        cols[1].selectbox("権限", ['member','owner'], index=['member','owner'].index(row['role']), key=f"role_{row['id']}", on_change=lambda uid=row['id']: update_user_role(uid))


def update_user_role(uid):
    new_role = st.session_state[f"role_{uid}"]
    conn.execute("UPDATE users SET role=? WHERE id=?", (new_role, uid))
    conn.commit()

# --- ページルーティング & ログアウト ---
if st.session_state['user'] is None:
    page = st.sidebar.radio("Navigate", ["ログイン", "新規登録"] )
    if page == "ログイン":
        login_page()
    else:
        signup_page()
else:
    # ログアウトボタン
    if st.sidebar.button("ログアウト"):    
        st.session_state['user'] = None
        st.session_state['role'] = None
        st.rerun()
        logout()

    menu = ["ダッシュボード", "取得リスト管理", "請求管理"]
    if st.session_state['role'] == 'owner':
        menu.append('メンバー管理')
    choice = st.sidebar.selectbox("メニュー", menu)
    if choice == "ダッシュボード":
        dashboard_page()
    elif choice == "取得リスト管理":
        list_management_page()
    elif choice == "請求管理":
        billing_page()
    elif choice == "メンバー管理":
        member_page()
