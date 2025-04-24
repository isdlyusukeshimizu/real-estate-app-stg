# merge_data.py
import pandas as pd
import datetime
import re

def merge_data(owner_info_path: str,
               zipcode_info_path: str,
               output_path: str,
               registry_office: str):
    """
    所有者情報CSVと郵便番号CSVを結合して、最終的なCSVを出力する
    """
    # 1) CSV読込
    df_owner = pd.read_csv(owner_info_path)
    df_zip   = pd.read_csv(zipcode_info_path)

    # 2) マージ（所有者住所で）
    df = pd.merge(df_owner, df_zip,
                  on='所有者住所', how='left')

    # 3) 情報取得日 と 担当法務局 を追加
    today = datetime.date.today().strftime('%Y-%m-%d')
    df['情報取得日'] = today
    df['担当法務局'] = registry_office

    # 4) 都道府県 と 顧客現在住所 に分割
    def split_pref(addr):
        m = re.match(r'(.+?[都道府県])(.+)', addr)
        if m:
            return m.group(1), m.group(2)
        else:
            return '', addr

    prefs, curr_addrs = zip(*df['所有者住所'].map(split_pref))
    df['都道府県']     = prefs
    df['顧客現在住所'] = curr_addrs

    # 5) 顧客相続住所 をコピー
    df['顧客相続住所'] = df['不動産所在地']

    # 6) 氏名 を 顧客名 にリネーム
    df.rename(columns={'氏名': '顧客名'}, inplace=True)

    # 7) 列の並び替え
    final = df[[
        '情報取得日',
        '顧客名',
        '郵便番号',
        '都道府県',
        '担当法務局',
        '顧客現在住所',
        '顧客相続住所'
    ]]

    # 8) CSV出力
    final.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ 結合完了: {output_path}")
