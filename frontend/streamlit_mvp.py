# frontend/streamlit_mvp.py の一番上に追加
import os, sys
# このファイル（streamlit_mvp.py）の親ディレクトリ (= project_root) を path に追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from dotenv import load_dotenv
import os
import pandas as pd
from io import StringIO

# 既存スクリプト群を import
from scripts.extract_info_from_pdf import ocr_pdf, extract_registry_office
from scripts.auto_mode_chatgpt import run_auto_mode
from scripts.pipeline import extract_owner_info
from scripts.concat_markitdown_extract_zipcode import get_zipcode
from scripts.merge_data import merge_data

load_dotenv()

st.title("不動産相続情報 MVP テスト")

# 1) PDF アップロード
uploaded = st.file_uploader("受付台帳 PDF をアップロード", type="pdf")
if not uploaded:
    st.info("PDF をアップロードしてください")
    st.stop()

if st.button("パイプライン実行→CSV 生成"):
    # 一時ファイルとして保存
    pdf_path = "./uploads/mvp_ledger.pdf"
    os.makedirs("./uploads", exist_ok=True)
    with open(pdf_path, "wb") as f:
        f.write(uploaded.getbuffer())

    st.text("▶️ OCR → 登記所抽出")
    text = ocr_pdf(pdf_path)
    registry_office = extract_registry_office(text)
    st.success(f"担当法務局: {registry_office}")

    st.text("▶️ 地番抽出 & PDF ダウンロード")
    pdf_paths = run_auto_mode(pdf_path)
    st.success(f"PDF ダウンロード: {len(pdf_paths)} 件")

    st.text("▶️ 所有者情報抽出")
    df_owner = extract_owner_info(pdf_paths)
    st.dataframe(df_owner)

    st.text("▶️ 郵便番号取得")
    zip_records = []
    for addr in df_owner["所有者住所"].unique():
        zip_records.append({
            "所有者住所": addr,
            "郵便番号": get_zipcode(addr)
        })
    df_zip = pd.DataFrame(zip_records)
    st.dataframe(df_zip)

    st.text("▶️ CSV 結合")
    # 一旦ローカル CSV に出力しておく
    owner_csv = "./uploads/owner_info.csv"
    zip_csv   = "./uploads/zipcode_info.csv"
    final_csv = "./uploads/final_output.csv"
    df_owner.to_csv(owner_csv, index=False, encoding="utf-8-sig")
    df_zip.to_csv(zip_csv,     index=False, encoding="utf-8-sig")

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
