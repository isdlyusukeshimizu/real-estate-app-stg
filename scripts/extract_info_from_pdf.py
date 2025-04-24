'''
PDFファイルから登記所の名前と相続関連の住所一覧を一括抽出するスクリプト
'''

from google.cloud import vision
from pdf2image import convert_from_path
from openai import OpenAI
from tempfile import TemporaryDirectory
import os
import io
import re
from dotenv import load_dotenv

load_dotenv()

# ── OpenAI クライアントの初期化 ──
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ── Google Vision 用認証情報のセットアップ ──
# streamlit_mvp.py で os.environ["GCP_SA_INFO_JSON"] にセットした文字列 JSON を読み込む
sa_info_json = os.getenv("GCP_SA_INFO_JSON")
if sa_info_json:
    sa_info = json.loads(sa_info_json)
    creds = service_account.Credentials.from_service_account_info(sa_info)
    vision_client = vision.ImageAnnotatorClient(credentials=creds)
else:
    # ローカル開発時に GOOGLE_APPLICATION_CREDENTIALS 環境変数経由で読み込みたい場合
    vision_client = vision.ImageAnnotatorClient()

def ocr_pdf(pdf_path: str) -> str:
    client_vision = vision.ImageAnnotatorClient()
    all_text = []
    with TemporaryDirectory() as tempdir:
        print("✅ PDF → 画像変換中...")
        images = convert_from_path(pdf_path, dpi=300, output_folder=tempdir, fmt='png')
        for idx, image in enumerate(images, 1):
            image_path = os.path.join(tempdir, f"page_{idx}.png")
            image.save(image_path, "PNG")
            print(f"📄 Page {idx} OCR実行中...")
            with open(image_path, "rb") as image_file:
                content = image_file.read()
            response = client_vision.document_text_detection(image=vision.Image(content=content))
            if response.error.message:
                print(f"❌ Page {idx} OCR失敗: {response.error.message}")
            else:
                all_text.append(response.full_text_annotation.text)
    return "\n".join(all_text)

def extract_registry_office(text_data: str) -> str:
    prompt = f"""
以下のOCRテキストから、冒頭に書かれている「登記所の名前」のみを抽出してください。
- 出力はその登記所名のみ（例：「大阪法務局」など）
- 余計な説明文や記号、接頭語、接尾語は出力しないでください
- 出力は一行だけ、名前だけにしてください

【テキスト開始】
{text_data}
【テキスト終了】
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    return response.choices[0].message.content.strip()

def extract_addresses(text_data: str) -> list[str]:
    prompt = f"""
以下のテキストは不動産登記の受付帳から抽出したOCR結果です。この中から、「所有権移転相続・法人合併」もしくは「所有権移転相続法人合併」と記載された登記行に該当する住所（例：「東近江市佐野町801 外2」など）のみをすべて抽出してください。

制約条件：
- 抽出対象は「所有権移転相続・法人合併」もしくは「所有権移転相続法人合併」と記載された行に限ります。
- 抽出するのは登記対象の住所部分のみ（「既)土地 〇〇市〇〇町〇〇番地 外〇」など）。
- 重複していてもすべて出力してください。
- 出力は1行に1住所、住所のみを出力してください。

【テキスト開始】
{text_data}
【テキスト終了】
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )

    # ① マークダウンの「1. 」などを除去 → 「-」や「・」なども除去
    raw_lines = [
        re.sub(r"^(\d+\.\s*|[-・\s]*)", "", line).strip()
        for line in response.choices[0].message.content.strip().splitlines()
    ]

    # ② 「都道府県市区町村」が含まれており、数字もある行を抽出
    filtered = [line for line in raw_lines if re.search(r'[都道府県市区町村].*\d', line)]

    # ③ 「外2」などを削除し、前後空白も除去
    return [re.sub(r"\s?外\s?\d+", "", addr).strip() for addr in filtered]


# 下記の関数で、なぜextract_addressesの引数にtext_data（登記所名）を加えているのか分からん
def get_cleaned_addresses(pdf_path: str) -> list[str]:
    text_data = ocr_pdf(pdf_path)
    return extract_addresses(text_data)

# 実行関数
def run(pdf_path: str):
    text_data = ocr_pdf(pdf_path)
    print("\n🧾 抽出結果:")
    print("■ 登記所名:")
    print(extract_registry_office(text_data))
    print("\n■ 住所一覧:")
    for addr in extract_addresses(text_data):
        print(addr)

# 実行例
if __name__ == "__main__":
    run("/mnt/c/Users/shish/Documents/ocr_doc_test-1-3.pdf")
