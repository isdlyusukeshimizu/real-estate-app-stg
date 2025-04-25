'''
このスクリプトからextract_info_from_pdf.pyを呼び出し、
OCR済みテキストから抽出した住所リストを取得し、
そのリストを使用して登記情報取得サイトに一度ログインし、
各住所の登記PDFを自動ダウンロードする。

営業時間外や重複住所は除外され、全処理後に自動でログアウトする。
'''

from scripts.extract_info_from_pdf import get_cleaned_addresses
from datetime import datetime, time as dtime
import holidays
import time
from playwright.sync_api import Playwright, sync_playwright
from pathlib import Path

JP_HOLIDAYS = holidays.Japan()

def is_within_service_hours(now: datetime) -> bool:
    # 年末年始は終日NG
    if datetime(now.year, 12, 29) <= now <= datetime(now.year + 1, 1, 3):
        return False
    
    is_holiday_or_weekend = now.weekday() >= 5 or now.date() in JP_HOLIDAYS
    
    if is_holiday_or_weekend:
        return dtime(8, 30) <= now.time() < dtime(18, 0)
    else:
        return dtime(8, 30) <= now.time() < dtime(23, 0)

def download_owner_info(page, address: str) -> None:
    now = datetime.now()
    if not is_within_service_hours(now):
        print(f"⚠️ 登記情報取得不可時間帯のためスキップ: {now.strftime('%Y-%m-%d %H:%M')} / {address}")
        return

    page.get_by_role("gridcell", name="不動産登記情報取得").locator("span").click()
    time.sleep(1)

    frame = page.frame(name="touki_search-iframe-frame")
    frame.locator("#check_direct_enable-inputEl").click()
    frame.locator("#direct_txt-inputEl").fill(address)
    time.sleep(1)
    frame.get_by_role("button", name="直接入力取込").click()
    frame.get_by_role("button", name="確定").click()
    frame.locator("img").click()
    time.sleep(1)

    frame.get_by_role("button", name="登記情報取得（オンライン）").click()
    time.sleep(1)
    frame.get_by_role("button", name="はい").click()
    time.sleep(1)
    frame.locator("#button-1005-btnEl").click()
    time.sleep(15)

    frame2 = page.frame(name="mypage_list-iframe-frame")
    frame2.locator("#ext-gen1323").get_by_role("button", name="PDF").click()

    with page.expect_download() as download_info:
        frame2.get_by_role("button", name="はい").click()
    download = download_info.value

    save_dir = Path("/mnt/c/Users/shish/Documents")
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{address.replace(' ', '_').replace('/', '-')}.pdf"
    download.save_as(str(save_path))
    print(f"✅ Downloaded PDF for: {address}")


def login_and_download_all(playwright, address_list):
    browser = playwright.chromium.launch(
        executable_path="/usr/bin/chromium",  # システムに入った Chromium を指定
        headless=True                         # サーバでは headless 推奨
    )
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.goto("https://xn--udk1b673pynnijsb3h8izqr1a.com/login.php")
    time.sleep(1)

    page.locator("input[name=\"id\"]").fill("NDVM3653")
    page.locator("input[name=\"id\"]").press("Tab")
    time.sleep(1)
    page.locator("input[name=\"pass\"]").fill("201810010009")
    time.sleep(1)
    page.get_by_role("button", name="利用規約に同意してログイン").click()
    time.sleep(1)

    for idx, address in enumerate(address_list):
        print(f"\n▶️ ({idx+1}/{len(address_list)}) 処理開始: {address}")
        try:
            download_owner_info(page, address)
        except Exception as e:
            print(f"❌ エラー発生: {address}\n{e}")
        print("⏳ 次の住所まで5秒待機中...\n")
        time.sleep(5)

    # ログアウト処理
    context.close()
    browser.close()

# 最後の方に追加
def run_auto_mode(pdf_path: str = "./uploads/ocr_doc_test-1-3-3.pdf") -> list[str]:
    cleaned_addresses = get_cleaned_addresses(pdf_path)
    address_list = sorted(set(cleaned_addresses))

    saved_paths = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/chromium",  # システムに入った Chromium を指定
            headless=True                         # サーバでは headless 推奨
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto("https://xn--udk1b673pynnijsb3h8izqr1a.com/login.php")
        time.sleep(1)

        page.locator("input[name=\"id\"]").fill("NDVM3653")
        page.locator("input[name=\"id\"]").press("Tab")
        time.sleep(1)
        page.locator("input[name=\"pass\"]").fill("201810010009")
        time.sleep(1)
        page.get_by_role("button", name="利用規約に同意してログイン").click()
        time.sleep(1)

        for idx, address in enumerate(address_list):
            print(f"\n▶️ ({idx+1}/{len(address_list)}) 処理開始: {address}")
            try:
                now = datetime.now()
                # if not is_within_service_hours(now):
                #     print(f"⚠️ 時間外スキップ: {address}")
                #     continue

                page.get_by_role("gridcell", name="不動産登記情報取得").locator("span").click()
                time.sleep(1)

                frame = page.frame(name="touki_search-iframe-frame")
                frame.locator("#check_direct_enable-inputEl").click()
                frame.locator("#direct_txt-inputEl").fill(address)
                time.sleep(1)
                frame.get_by_role("button", name="直接入力取込").click()
                frame.get_by_role("button", name="確定").click()
                frame.locator("img").click()
                time.sleep(1)

                frame.get_by_role("button", name="登記情報取得（オンライン）").click()
                time.sleep(1)
                frame.get_by_role("button", name="はい").click()
                time.sleep(1)
                frame.locator("#button-1005-btnEl").click()
                time.sleep(1)

                frame2 = page.frame(name="mypage_list-iframe-frame")
                frame2.locator("#ext-gen1323").get_by_role("button", name="PDF").click()

                with page.expect_download() as download_info:
                    frame2.get_by_role("button", name="はい").click()
                download = download_info.value

                save_dir = Path("/mnt/c/Users/shish/Documents")
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / f"{address.replace(' ', '_').replace('/', '-')}.pdf"
                download.save_as(str(save_path))
                saved_paths.append(str(save_path))

                print(f"✅ Downloaded PDF for: {address}")

            except Exception as e:
                print(f"❌ エラー発生: {address}\n{e}")
            print("⏳ 次の住所まで10秒待機中...\n")
            time.sleep(10)

        context.close()
        browser.close()

    return saved_paths  # 最後に保存したファイルパスを返す


# 🔒メイン実行処理、他ファイルからimportしたときは実行されないようにしてる
# 下記は、このファイルが直接実行されたときだけ」中のコードを実行するための仕組み
if __name__ == "__main__":
    pdf_path = "/mnt/c/Users/shish/Documents/ocr_doc_test-1-3.pdf"
    cleaned_addresses = get_cleaned_addresses(pdf_path)
    print("cleaned_addresses", cleaned_addresses)
    address_list = sorted(set(cleaned_addresses))

    with sync_playwright() as playwright:
        login_and_download_all(playwright, address_list)

