# frontend/streamlit_mvp.py の一番上に追加
import os, sys
# プロジェクトルートをパスに追加（既に入っていれば不要ですが、念のため）
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import os
import streamlit as st
import shutil
import pandas as pd
from io import StringIO
import json

# ローカルでの環境変数読み込み（開発用）
# from dotenv import load_dotenv
# load_dotenv()

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



# カスタムモジュールのインポート
from scripts.extract_info_from_pdf import ocr_pdf, extract_registry_office
from scripts.auto_mode_chatgpt import run_auto_mode
from scripts.pipeline import extract_owner_info
from scripts.concat_markitdown_extract_zipcode import get_zipcode
from scripts.merge_data import merge_data

# ページ設定
st.set_page_config(page_title="不動産相続情報 MVP テスト", layout="wide")

st.title("不動産相続情報 MVP テスト")
st.text(f"pdfinfo binary: {shutil.which('pdfinfo')}")

# PDF アップロード
uploaded = st.file_uploader("受付台帳 PDF をアップロード", type="pdf")
if not uploaded:
    st.info("PDF をアップロードしてください")
    st.stop()

# ボタン押下でパイプライン実行
if st.button("パイプライン実行→CSV 生成"):
    with st.spinner("処理中です。しばらくお待ちください..."):
        # アップロード PDF を保存
        os.makedirs("uploads", exist_ok=True)
        pdf_path = os.path.join("uploads", "mvp_ledger.pdf")
        with open(pdf_path, "wb") as f:
            f.write(uploaded.getbuffer())

        # 1. OCR & 登記所抽出
        st.write("▶️ OCR → 登記所抽出")
        text = ocr_pdf(pdf_path)
        registry_office = extract_registry_office(text)
        st.success(f"担当法務局: {registry_office}")

        # 2. 地番抽出 & PDF ダウンロード
        st.write("▶️ 地番抽出 & PDF ダウンロード")
        save_dir = "downloads"
        os.makedirs(save_dir, exist_ok=True)
        pdf_paths = run_auto_mode(pdf_path, save_dir=save_dir)  # ← 引数追加
        st.success(f"PDF ダウンロード: {len(pdf_paths)} 件")

        # 3. 所有者情報抽出
        st.write("▶️ 所有者情報抽出")
        df_owner = extract_owner_info(pdf_paths)
        st.dataframe(df_owner)

        # 4. 郵便番号取得
        st.write("▶️ 郵便番号取得")
        zip_records = []
        st.write("df_owner columns:", df_owner.columns.tolist())
        for addr in df_owner["所有者住所"].unique():
            zip_records.append({
                "所有者住所": addr,
                "郵便番号": get_zipcode(addr)
            })
        df_zip = pd.DataFrame(zip_records)
        st.dataframe(df_zip)

        # 5. CSV 結合
        st.write("▶️ CSV 結合")
        owner_csv = os.path.join("uploads", "owner_info.csv")
        zip_csv = os.path.join("uploads", "zipcode_info.csv")
        final_csv = os.path.join("uploads", "final_output.csv")
        df_owner.to_csv(owner_csv, index=False, encoding="utf-8-sig")
        df_zip.to_csv(zip_csv, index=False, encoding="utf-8-sig")

        merge_data(owner_csv, zip_csv, final_csv, registry_office)
        st.success("✅ 最終 CSV 生成完了")

        # ダウンロードボタン
        with open(final_csv, "rb") as f:
            st.download_button(
                label="最終 CSV をダウンロード",
                data=f,
                file_name="final_output.csv",
                mime="text/csv"
            )
