# pipeline.py
import argparse
import re
import pandas as pd
from openai import OpenAI
from markitdown import MarkItDown
from scripts.extract_info_from_pdf import ocr_pdf, extract_registry_office
from scripts.auto_mode_chatgpt import run_auto_mode
from scripts.concat_markitdown_extract_zipcode import get_zipcode
from scripts.merge_data import merge_data
from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def extract_owner_info(pdf_paths):
    """
    ダウンロード済みの所有者情報PDFを解析し、氏名・所有者住所・不動産所在地を抽出してDataFrameを返す
    """
    client = OpenAI(api_key=OPENAI_API_KEY)  # 環境変数推奨
    md = MarkItDown()
    records = []

    for pdf_path in pdf_paths:
        # 1) PDF→テキスト
        result = md.convert(pdf_path)
        text_data = result.text_content

        # 2) GPTプロンプト送信
        prompt = f"""
以下は登記簿のOCRテキストです。この中から以下の情報を抽出してください。

1. 「原因」が「相続」または「遺贈」である所有権移転に関して、**最も新しい**氏名とその所有者住所（共有者の住所）。
2. その相続によって取得された不動産の所在地（住所）。

- 出力形式:
  氏名: ○○○○
  所有者住所: ○○県○○市○○…
  不動産所在地: ○○県○○市○○…

【テキスト開始】
{text_data}
【テキスト終了】
"""
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user","content":prompt}],
            temperature=0.0
        )
        output = resp.choices[0].message.content.strip()

        # 3) 正規表現で抽出
        name_m = re.search(r"氏名:\s*(.+)", output)
        addr_m = re.search(r"所有者住所:\s*(.+)", output)
        prop_m = re.search(r"不動産所在地:\s*(.+)", output)
        if name_m and addr_m and prop_m:
            records.append({
                "PDFファイル": pdf_path,
                "氏名": name_m.group(1).strip(),
                "所有者住所": addr_m.group(1).strip(),
                "不動産所在地": prop_m.group(1).strip()
            })

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description='不動産相続情報パイプライン')
    parser.add_argument('--ledger-pdf',   required=True,               help='受付台帳PDFパス')
    parser.add_argument('--owner-out',    default='owner_info.csv',    help='出力: 所有者情報CSV')
    parser.add_argument('--zipcode-out',  default='zipcode_info.csv',  help='出力: 郵便番号CSV')
    parser.add_argument('--final-out',    default='final_output.csv',  help='出力: 統合CSV')
    args = parser.parse_args()

    # ステップ0: 担当法務局取得
    print("▶️ 担当法務局取得開始")
    text_data = ocr_pdf(args.ledger_pdf)
    registry_office = extract_registry_office(text_data)
    print(f"✅ 担当法務局: {registry_office}")

    # ステップ1: 地番抽出 & PDFダウンロード
    print("▶️ 地番抽出とPDFダウンロード開始")
    pdf_paths = run_auto_mode(args.ledger_pdf)
    print(f"✅ PDFダウンロード完了: {len(pdf_paths)} 件")

    # ステップ2: 所有者情報抽出
    print("▶️ 所有者情報抽出開始")
    df_owner = extract_owner_info(pdf_paths)
    df_owner.to_csv(args.owner_out, index=False, encoding='utf-8-sig')
    print(f"✅ 所有者情報CSV出力: {args.owner_out}")

    # ステップ3: 郵便番号取得
    print("▶️ 郵便番号検索開始")
    zip_records = []
    for addr in df_owner['所有者住所'].unique():
        zipcode = get_zipcode(addr)
        zip_records.append({'所有者住所': addr, '郵便番号': zipcode})
    df_zip = pd.DataFrame(zip_records)
    df_zip.to_csv(args.zipcode_out, index=False, encoding='utf-8-sig')
    print(f"✅ 郵便番号CSV出力: {args.zipcode_out}")

    # ステップ4: CSV結合
    print("▶️ CSV結合開始")
    merge_data(
        args.owner_out,
        args.zipcode_out,
        args.final_out,
        registry_office
    )
    print(f"✅ 最終CSV出力: {args.final_out}")


if __name__ == '__main__':
    main()
