'''
このスクリプトは、不動産登記PDFから最新の「相続」または「遺贈」による所有権移転情報を抽出し、
所有者の住所から郵便番号を自動的に取得して表示する処理を行う。

【主な処理の流れ】
1. 必要なライブラリ（OpenAI, MarkItDown, pandas, re, unicodedata）をインポート
2. 郵便番号検索に使用するKEN_ALL.CSVファイルを読み込み、適切な列名を設定
3. 漢数字（○丁目）をアラビア数字に変換するマップと関数を定義
4. 住所から都道府県・市区町村・町域を抽出し、KEN_ALLデータから該当する郵便番号を返す関数を定義
5. MarkItDownを用いて指定したPDFファイルをテキストに変換
6. OpenAI GPT-4oに対して、抽出したテキストの中から「最新の相続・遺贈の所有者氏名と住所」を抽出するプロンプトを送信
7. GPTの応答から所有者住所を抽出し、先ほどの関数を用いて郵便番号を取得・表示

【出力】
- 所有者住所が正常に抽出できた場合：該当する郵便番号を表示
- 抽出に失敗した場合：エラーメッセージを表示
'''

from openai import OpenAI
from markitdown import MarkItDown
import pandas as pd
import re
import unicodedata
import sys
from scripts.auto_mode_chatgpt import run_auto_mode
import os
from dotenv import load_dotenv

load_dotenv()

KEN_ALL_CSV_PATH = os.getenv("KEN_ALL_CSV_PATH")

# 日本郵便KEN_ALL.CSV読み込み
df = pd.read_csv(
    KEN_ALL_CSV_PATH,
    encoding="shift_jis",
    header=None
)
df.columns = [
    "地域コード", "変更フラグ", "郵便番号", 
    "都道府県カナ", "市区町村カナ", "町域カナ",
    "都道府県", "市区町村", "町域", 
    "フラグ1", "フラグ2", "フラグ3", 
    "フラグ4", "フラグ5", "フラグ6"
]

KANJI_NUM_MAP = {
    '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
    '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'
}

def kanji_to_arabic(text):
    for kanji, num in KANJI_NUM_MAP.items():
        text = text.replace(kanji + '丁目', num + '丁目')
    return text

def get_zipcode(address: str) -> str:
    """
    住所文字列から郵便番号を検索して返す
    """
    address = unicodedata.normalize("NFKC", address)
    address = kanji_to_arabic(address)
    address = re.sub(r"字", "", address)

    m = re.match(r"(..[都道府県])(.+?[市区町村])(.+)", address)
    if not m:
        raise ValueError("住所の形式が不正です: " + address)
    pref, city, rest = m.groups()
    rest = rest.split()[0]
    town = re.split(r"[\d\-－ー0-9]", rest)[0]

    result = df[
        (df["都道府県"] == pref) &
        (df["市区町村"] == city) &
        (df["町域"] == town)
    ]
    if result.empty:
        result = df[
            (df["都道府県"] == pref) &
            (df["市区町村"] == city) &
            (df["町域"].str.contains(town))
        ]
    if not result.empty:
        zip7 = str(result.iloc[0]["郵便番号"]).zfill(7)
        return f"{zip7[:3]}-{zip7[3:]}"
    return "該当なし"

# テスト用メイン関数
def main():
    # PDFダウンロード実行
    print("▶️ Step1: PDFの自動ダウンロード開始")
    paths = run_auto_mode()
    print("✅ ダウンロード完了:")
    for p in paths:
        print(f" - {p}")

    # 主な処理の確認用に、最初の一件だけ郵便番号をテスト
    if paths:
        sample_address = paths[0]
        zipc = get_zipcode(sample_address)
        print(f"▶️ テスト: {sample_address} の郵便番号: {zipc}")

if __name__ == "__main__":
    main()
