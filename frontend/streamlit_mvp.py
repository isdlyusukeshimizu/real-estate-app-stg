import os, sys, json

# ── VSCode/Streamlit CLI からの相対パス解決──
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import streamlit as st
import shutil
import pandas as pd

# 1. KEN_ALL.CSV (data/x-ken-all.csv) を環境変数にセット
csv_rel = os.path.join("data", "x-ken-all.csv")
csv_abspath = os.path.join(ROOT, csv_rel)
os.environ["KEN_ALL_CSV_PATH"] = csv_abspath

# 2. OpenAI APIキーを secrets から取得して環境変数にセット
openai_key = st.secrets["OPENAI_API_KEY"]
os.environ["OPENAI_API_KEY"] = openai_key

# 3. GCP サービスアカウント情報を一時ファイルに書き出し
gcp_sa = st.secrets["gcp_service_account"]  # TOML 内で { type=..., project_id=..., ... } の dict
creds_path = os.path.join(ROOT, "gcp_creds.json")
with open(creds_path, "w") as f:
    json.dump(gcp_sa, f)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

# ── ここまでで各スクリプトが必要とする環境変数をセット完了 ──

# カスタムモジュールをインポート
from scripts.extract_info_from_pdf import ocr_pdf, extract_registry_office
from scripts.auto_mode_chatgpt    import run_auto_mode
from scripts.pipeline             import extract_owner_info
from scripts.concat_markitdown_extract_zipcode import get_zipcode
from scripts.merge_data           import merge_data

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
        pdf_paths = run_auto_mode(pdf_path)
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
