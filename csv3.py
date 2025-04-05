# -*- coding: utf-8 -*-
# --- ライブラリインポート ---
#Windows Virtual Environment Activation: .\.venv\Scripts\activate.ps1
import json
import os
import sys # sys.exit()のために追加
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementClickInterceptedException,
    WebDriverException, NoSuchWindowException, StaleElementReferenceException,
    InvalidSessionIdException
)
import time
import re
import traceback
import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# --- グローバル変数・設定 ---
CHROME_DRIVER_PATH = None # ChromeDriverのパス (Noneの場合は自動検出)
USER_EMAIL = 'Email' # ログインに使用するメールアドレス
USER_PASSWORD = 'Password' # ログインに使用するパスワード
OUTPUT_DIR_NAME = 'syllabus_output' # 出力ディレクトリ名
OUTPUT_JSON_FILE = 'syllabus_data.json' # 出力JSONファイル名
TARGET_FIELDS = ["基盤科目", "先端科目", "特設科目"] # スクレイピング対象の分野
TARGET_YEARS = [2025, 2024, 2023] # スクレイピング対象の年度
HEADLESS_MODE = False # Trueにするとヘッドレスモードで実行
PAGE_LOAD_TIMEOUT = 45 # ページの読み込みタイムアウト時間(秒)
ELEMENT_WAIT_TIMEOUT = 60 # 要素が表示されるまでの最大待機時間(秒)
SHORT_WAIT = 3 # 短い待機時間(秒)
MEDIUM_WAIT = 5 # 中程度の待機時間(秒)
LONG_WAIT = 10 # 長い待機時間(秒)
# ★★★ 英語ページでのJSレンダリング待機時間 ★★★
JS_RENDER_WAIT = 10 # 秒 (必要に応じて調整)

# --- ★ カスタム例外クラス ★ ---
class MissingCriticalDataError(Exception):
    """必須データまたは定義済みデータが取得できなかった場合に発生させる例外"""
    pass

# --- ヘルパー関数 ---

def create_output_dirs(base_dir=OUTPUT_DIR_NAME):
    """
    出力用のディレクトリ（ベース、ログ、スクリーンショット）を作成する。
    """
    logs_dir = os.path.join(base_dir, "logs") # ログ用ディレクトリパス
    screenshots_dir = os.path.join(base_dir, "screenshots") # スクリーンショット用ディレクトリパス
    for dir_path in [base_dir, logs_dir, screenshots_dir]:
        os.makedirs(dir_path, exist_ok=True) # exist_ok=True で既に存在してもエラーにしない
    return base_dir, logs_dir, screenshots_dir

def save_screenshot(driver, prefix="screenshot", dir_path="screenshots"):
    """
    現在の画面のスクリーンショットを指定されたディレクトリに保存する。
    ファイル名にはタイムスタンプが付与される。
    WebDriverが無効な場合やセッションエラー時はNoneを返す。
    """
    if not driver or not hasattr(driver, 'session_id') or driver.session_id is None:
        print("[警告] WebDriverが無効またはセッションIDがないため、スクリーンショットを保存できません。")
        return None
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S") # 現在時刻のタイムスタンプ
        filename = f"{prefix}_{timestamp}.png" # ファイル名生成
        filepath = os.path.join(dir_path, filename) # フルパス生成
        driver.save_screenshot(filepath) # スクリーンショット保存
        print(f"スクリーンショットを保存しました: {filepath}")
        return filepath
    except InvalidSessionIdException:
        print("[警告] スクリーンショット保存試行中にInvalidSessionIdExceptionが発生しました。")
        return None
    except WebDriverException as e:
        # Handle specific WebDriver exceptions if necessary
        if "target window already closed" in str(e).lower():
             print("[警告] スクリーンショット保存試行中にウィンドウが閉じられました。")
        else:
             print(f"[エラー] スクリーンショットの保存に失敗: {e}")
        return None
    except Exception as e:
        print(f"[エラー] スクリーンショット保存中に予期せぬエラー: {e}")
    return None

def normalize_text(text):
    """
    文字列内の空白文字を正規化する。
    全角スペースを半角に、連続する空白を1つにし、前後の空白を削除する。
    """
    if isinstance(text, str):
        text = text.replace('　', ' ') # 全角スペースを半角に
        text = re.sub(r'\s+', ' ', text) # 連続する空白文字(スペース、タブ、改行など)を1つのスペースに
        return text.strip() # 前後の空白を削除
    return "" # 文字列でない場合は空文字を返す

def click_element(driver, element, wait_time=SHORT_WAIT):
    """
    指定された要素をクリックする。
    ElementClickInterceptedExceptionが発生した場合はJavaScriptでクリックを試みる。
    StaleElementReferenceExceptionやその他のエラー発生時はFalseを返す。
    セッション/ウィンドウエラーは上位に伝播させる。
    """
    try:
        # 要素がクリック可能になるまで待機
        WebDriverWait(driver, wait_time).until(EC.element_to_be_clickable(element))
        element.click() # クリック実行
        time.sleep(0.5) # クリック後の少し長めの待機 (ページの反応を待つ)
        return True
    except ElementClickInterceptedException:
        # 通常のクリックが妨害された場合、JavaScriptでクリックを試みる
        try:
            # 要素を画面内にスクロール
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
            time.sleep(0.3)
            # JavaScriptでクリック実行
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.5) # JSクリック後も少し待つ
            return True
        except Exception as js_e:
            print(f"        JavaScript Click中にエラー: {js_e}")
            return False
    except StaleElementReferenceException:
        # 要素が古くなった（DOMから削除されたなど）場合
        print("        Click試行中に要素がStaleになりました。再取得が必要です。")
        return False
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        # セッションIDが無効、またはウィンドウが存在しない場合
        print(f"        Click中にセッション/ウィンドウエラー: {e_session}")
        raise # このエラーは致命的なので上位に伝播させる
    except Exception as e:
        # その他の予期せぬエラー
        print(f"        Click中に予期せぬエラー: {e}")
        return False

def select_option_by_text(driver, select_element, option_text, fallback_to_js=True):
    """
    Select要素から表示テキストでオプションを選択する。
    通常の選択が失敗した場合、JavaScriptによる選択を試みる (fallback_to_js=Trueの場合)。
    """
    try:
        # Selectオブジェクトを作成
        select_obj = Select(select_element)
        # 表示テキストでオプションを選択
        select_obj.select_by_visible_text(option_text)
        time.sleep(0.3) # 選択反映のための待機
        # 選択されたオプションを再取得して確認
        selected_option = Select(select_element).first_selected_option
        if selected_option.text.strip() == option_text:
            return True # 正常に選択された
        else:
            # 選択が反映されなかった場合 (まれに発生)
            raise Exception("Selection did not reflect correctly.")
    except Exception as e:
        # 通常の選択が失敗した場合
        if fallback_to_js:
            # JavaScriptによる選択を試みる
            try:
                js_script = f"""
                    let select = arguments[0]; let optionText = arguments[1];
                    for(let i = 0; i < select.options.length; i++) {{
                        if(select.options[i].text.trim() === optionText) {{
                            select.selectedIndex = i;
                            // changeイベントとinputイベントを発火させて選択を反映させる
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true; // 該当オプションが見つかり選択成功
                        }}
                    }}
                    return false; // 該当オプションが見つからなかった
                """
                # JavaScriptを実行
                result = driver.execute_script(js_script, select_element, option_text)
                if result:
                    time.sleep(0.5) # JS実行後の待機
                    # JSで選択されたテキストを再確認
                    selected_option_text_js = driver.execute_script("return arguments[0].options[arguments[0].selectedIndex].text.trim();", select_element)
                    return selected_option_text_js == option_text # 期待通りか確認
                else:
                    # JavaScriptでもオプションが見つからなかった場合
                    return False
            except (InvalidSessionIdException, NoSuchWindowException) as e_session:
                print(f"        JS選択中にセッション/ウィンドウエラー: {e_session}")
                raise # 致命的エラー
            except Exception as js_error:
                print(f"      JavaScriptによる選択中にエラー: {js_error}")
                return False
        else:
             # フォールバックが無効な場合は失敗
             return False

def get_text_by_xpath(driver, xpath, default=""):
    """指定されたXPathの要素のテキストを取得するヘルパー関数"""
    try:
        # 指定XPathの要素が存在するまで待機
        element = WebDriverWait(driver, SHORT_WAIT).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # テキストを取得し正規化
        text_content = normalize_text(element.text)
        # テキストが存在すればそれを、なければデフォルト値を返す
        return text_content if text_content else default
    except (TimeoutException, NoSuchElementException):
        return default
    except StaleElementReferenceException:
        print(f"   [警告] get_text_by_xpath: 要素がStaleになりました ({xpath})。デフォルト値「{default}」を使用。")
        return default
    except Exception as e:
        print(f"   [警告] get_text_by_xpath: 予期せぬエラー ({xpath}): {e}。デフォルト値「{default}」を使用。")
        return default

def generate_english_url(current_url):
    """現在のURLに lang=en パラメータを追加または置換して返す"""
    try:
        parsed_url = urlparse(current_url) # URLをパース
        query_params = parse_qs(parsed_url.query) # クエリパラメータを辞書として取得
        query_params['lang'] = ['en'] # langパラメータをenに設定（存在すれば上書き）
        new_query = urlencode(query_params, doseq=True) # 新しいクエリ文字列を作成 (doseq=Trueでリスト値に対応)
        # 新しいURLを構築
        english_url = urlunparse((
            parsed_url.scheme, parsed_url.netloc, parsed_url.path,
            parsed_url.params, new_query, parsed_url.fragment
        ))
        return english_url
    except Exception as e:
        print(f"   [警告] 英語URLの生成に失敗: {e}。元のURLを返します: {current_url}")
        return current_url # 失敗した場合は元のURLを返す

# --- ★★★ get_syllabus_details 関数の修正 ★★★ ---
def get_syllabus_details(driver, current_year, screenshots_dir):
    """
    シラバス詳細ページから指定された日本語と英語の情報を取得。
    """
    details_ja = {'year_scraped': current_year} # スクレイピングした年度を記録
    details_en_table_rerun = {} # 英語ページで再取得したテーブルデータ用
    japanese_url = "N/A"

    # --- 1. 日本語ページの情報をまず取得 ---
    try:
        japanese_url = driver.current_url # 現在のURL (日本語版のはず)
        print(f"     日本語ページ処理中: {japanese_url}")
        # ページの基本要素(body)が表示されるまで待機
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(MEDIUM_WAIT) # JS描画などを考慮して少し長めに待機

        # --- Course ID 取得 (日本語ページで取得) ---
        details_ja['course_id'] = None
        try:
            # URLから 'id=' または 'entno=' パラメータ、またはパス中の数字を抽出
            id_match = re.search(r'[?&](?:id|entno)=(\d+)', japanese_url) or \
                       re.search(r'/syllabus/(\d+)', japanese_url)
            if id_match:
                details_ja['course_id'] = id_match.group(1)
            else:
                # URLから取得できない場合、テーブルの「登録番号」や隠し要素からも試す
                try:
                    # テーブルの「登録番号」欄から取得
                    reg_num = get_text_by_xpath(driver, "//tr[th[normalize-space()='登録番号']]/td")
                    if reg_num and reg_num.isdigit():
                        details_ja['course_id'] = reg_num
                    else:
                         # 隠しinput要素 (nameに 'id' や 'entno' を含む) から取得
                         hidden_elements = driver.find_elements(By.XPATH, "//input[@type='hidden' and (contains(@name, 'id') or contains(@name, 'entno'))]")
                         for hidden in hidden_elements:
                             value = hidden.get_attribute('value')
                             if value and value.isdigit():
                                 details_ja['course_id'] = value
                                 break # 最初に見つかったものを採用
                except Exception:
                    pass # テーブルや隠し要素からの取得失敗はここでは無視
        except Exception as e:
            print(f"   [警告] Course ID の取得中にエラー: {e}")

        # Course IDがどうしても取得できない場合は、必須データ欠落としてエラーを発生させる
        if not details_ja.get('course_id'):
            raise MissingCriticalDataError(f"必須データ(Course ID)の取得に失敗 (URL: {japanese_url})")

        # --- ★★★ 日本語情報の取得マップ定義 (指定されたフィールドのみ) ★★★ ---
        info_map_ja = {
            'name': ("科目名", "//h2[@class='class-name']", f"名称不明-{details_ja['course_id']}"),
            'semester': ("学期", "//tr[th[normalize-space()='年度・学期']]/td", "学期不明"),
            'professor': ("担当者名", "//tr[th[contains(text(),'担当者名')]]/td", ""), # 空を許容
            'credits': ("単位", "//tr[th[contains(text(),'単位')]]/td", "単位不明"),
            'field': ("分野", "//tr[th[contains(text(),'分野')]]/td", "分野不明"),
            'location': ("教室", "//tr[th[contains(text(),'教室')]]/td", "教室不明"),
            'day_period': ("曜日時限", "//tr[th[contains(text(),'曜日時限')]]/td", "曜日時限不明"),
            'selection_method': ("選抜方法", "//tr[th[contains(text(),'選抜方法')]]/td", ""), # 空を許容
        }
        # ★ 不適切と判断する科目名のパターン (例: 検索結果一覧ページのタイトルなど)
        INVALID_COURSE_NAME_PATTERNS = ["慶應義塾大学 シラバス・時間割"]

        critical_data_missing = False # 必須データ欠落フラグ
        missing_details = [] # 欠落したデータの詳細リスト
        # ★★★ 取得対象のキーリスト (エラーチェック用) ★★★
        target_keys = list(info_map_ja.keys())

        print("     --- 日本語情報取得開始 ---")
        # --- 日本語情報取得ループ ---
        for key, (label, xpath, default_value, *_) in info_map_ja.items():
            print(f"       日本語 {label} 取得試行...")
            details_ja[key] = get_text_by_xpath(driver, xpath, default_value)

            # ★★★ 必須チェック (担当者名、選抜方法以外) ★★★
            if key not in ['professor', 'selection_method']:
                if key == 'name':
                    # 科目名がデフォルト値と同じか、不適切パターンに含まれる場合
                    if details_ja[key] == default_value or any(pattern in details_ja[key] for pattern in INVALID_COURSE_NAME_PATTERNS):
                        critical_data_missing = True
                        missing_details.append(f"{label}(ja): 不適切「{details_ja[key]}」")
                # その他の必須項目がデフォルト値と同じか空文字の場合
                elif details_ja[key] == default_value or not details_ja[key]:
                    critical_data_missing = True
                    missing_details.append(f"{label}(ja): 未取得/空")

        # --- 日本語の必須データ取得で失敗があれば、ここでスクリプト停止 ---
        if critical_data_missing:
            raise MissingCriticalDataError(f"必須日本語データ取得失敗 (URL: {japanese_url}): {'; '.join(missing_details)}")
        print("     --- 日本語情報取得完了 ---")

    # --- 日本語ページ取得時の各種エラーハンドリング ---
    except TimeoutException as e_timeout:
        print(f"   [エラー] 日本語ページ({japanese_url})の基本要素読み込みタイムアウト。スキップします。 {e_timeout}")
        save_screenshot(driver, f"detail_ja_load_timeout_{current_year}", screenshots_dir)
        return None
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        print(f"   [エラー] 日本語ページ処理中にセッション/ウィンドウエラー: {e_session}")
        raise
    except MissingCriticalDataError as e_critical:
        print(f"   [エラー] {e_critical}")
        save_screenshot(driver, f"detail_ja_critical_missing_{current_year}", screenshots_dir)
        raise
    except Exception as e_ja:
        print(f"   [エラー] 日本語ページ({japanese_url})の処理中に予期せぬエラー: {e_ja}")
        save_screenshot(driver, f"detail_ja_unknown_error_{current_year}", screenshots_dir)
        traceback.print_exc()
        return None

    # --- 2. 英語ページの情報を取得 ---
    english_url = generate_english_url(japanese_url) # 英語ページのURLを生成
    print(f"     英語ページ処理中: {english_url}")
    try:
        driver.get(english_url) # 英語ページにアクセス
        # ページの基本要素(body)が表示されるまで待機
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"     英語ページ読み込み完了。JavaScriptレンダリング待機中 ({JS_RENDER_WAIT}秒)...")
        time.sleep(JS_RENDER_WAIT) # ★★★ JSレンダリング待機 ★★★
        print(f"     待機完了。英語情報取得試行...")
        print("     --- 英語情報取得開始 ---")

        # --- ★★★ 英語ページのテーブルデータを再取得試行 (指定フィールドのみ) ★★★ ---
        for key in target_keys: # info_map_ja のキーを使用
            if key in info_map_ja:
                label, xpath, _, *_ = info_map_ja[key] # 日本語マップからXPath取得
                print(f"       英語 {label}(テーブル再取得) 取得試行...")
                # 英語ページで同じXPathを使ってテーブルテキスト取得を試みる
                details_en_table_rerun[key] = get_text_by_xpath(driver, xpath, "") # 取得失敗は許容
        print("     --- 英語情報取得完了 ---")

    # --- 英語ページ取得時のエラーハンドリング (エラーでも続行) ---
    except TimeoutException as e_timeout_en:
        print(f"   [警告] 英語ページ({english_url})の読み込みタイムアウト。英語情報は一部欠落します。 {e_timeout_en}")
        save_screenshot(driver, f"detail_en_load_timeout_{current_year}", screenshots_dir)
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        print(f"   [エラー] 英語ページ処理中にセッション/ウィンドウエラー: {e_session}")
        raise
    except Exception as e_en:
        print(f"   [警告] 英語ページ({english_url})の処理中に予期せぬエラー: {e_en}。英語情報は一部欠落します。")
        save_screenshot(driver, f"detail_en_unknown_error_{current_year}", screenshots_dir)
        traceback.print_exc()

    # --- 3. 日本語情報と英語情報をマージ ---
    final_details = {
        'course_id': details_ja['course_id'],
        'year_scraped': details_ja['year_scraped'],
        'translations': { 'ja': {}, 'en': {} } # 日本語と英語の情報を格納する辞書
    }
    # ★★★ コピー対象キーを target_keys に限定 ★★★
    all_keys_to_copy = target_keys

    # 日本語情報を final_details に設定
    for key in all_keys_to_copy:
        final_details['translations']['ja'][key] = details_ja.get(key, "")

    # 英語情報を final_details に設定 (優先度考慮)
    for key in all_keys_to_copy:
        ja_value = details_ja.get(key, "") # 対応する日本語の値
        en_value_to_set = ja_value # デフォルトは日本語の値をコピー

        # 優先1: 英語ページで再取得したテーブルデータを確認
        rerun_value = details_en_table_rerun.get(key)
        if rerun_value: # 再取得データが存在する場合 (キーは target_keys なのでテーブルデータのみ)
            is_plausibly_english = False # 英語らしい値かどうかのフラグ
            # キーに応じて英語らしく見えるか判定
            if key in ['name', 'professor', 'field', 'location', 'selection_method']:
                if rerun_value != ja_value and re.search(r'[a-zA-Z]', rerun_value):
                    is_plausibly_english = True
            elif key == 'semester':
                is_plausibly_english = any(eng_term.lower() in rerun_value.lower() for eng_term in ["Spring", "Fall", "Summer", "Winter", "Year"])
            elif key == 'day_period':
                is_plausibly_english = any(eng_day in rerun_value for eng_day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
            elif key == 'credits':
                # 単位は数字や英語("Unit")を含むか、日本語と異なる場合に英語とみなす
                if (re.search(r'\d', rerun_value) and re.search(r'[a-zA-Z]', rerun_value)) or \
                   re.fullmatch(r'[\d.]+', rerun_value) or \
                   (rerun_value != ja_value and re.search(r'[a-zA-Z]', rerun_value)):
                     is_plausibly_english = True


            if is_plausibly_english:
                en_value_to_set = rerun_value # 英語らしい値を採用

        # 優先2: 日本語からの変換を試行 (上記で英語値が設定されなかった場合)
        if en_value_to_set == ja_value: # まだ日本語の値のままの場合
            if key == 'semester':
                sem_map = {"春学期": "Spring", "秋学期": "Fall", "通年": "Full Year", "春": "Spring", "秋": "Fall"}
                matched_jp_key = None
                for jp_key in sem_map:
                    if jp_key in ja_value: matched_jp_key = jp_key; break
                if matched_jp_key: en_value_to_set = ja_value.replace(matched_jp_key, sem_map[matched_jp_key]).strip()

            elif key == 'day_period':
                day_map = {"月": "Mon", "火": "Tue", "水": "Wed", "木": "Thu", "金": "Fri", "土": "Sat", "日": "Sun"}
                parts = ja_value.split()
                if len(parts) >= 1 and parts[0] in day_map:
                    en_value_to_set = f"{day_map[parts[0]]} {' '.join(parts[1:])}".strip()

        # 最終的な英語の値を設定
        final_details['translations']['en'][key] = en_value_to_set

    # --- トップレベルの semester, professor_ja, name_ja, field_ja, credits_ja を設定 (集約用) ---
    # これらの情報は aggregation_key の作成に必要
    final_details['semester'] = final_details['translations']['en'].get('semester') or final_details['translations']['ja'].get('semester', '不明')
    final_details['professor_ja'] = final_details['translations']['ja'].get('professor', '')
    final_details['name_ja'] = final_details['translations']['ja'].get('name', '')
    final_details['field_ja'] = final_details['translations']['ja'].get('field', '')
    final_details['credits_ja'] = final_details['translations']['ja'].get('credits', '')


    print(f"       ✓ 詳細情報取得完了: 「{final_details['translations']['ja'].get('name', '不明')}」")
    return final_details


# --- ★★★ aggregate_syllabus_data 関数の修正 ★★★ ---
def aggregate_syllabus_data(all_raw_data):
    """
    複数年度にわたる生データを集約し、指定されたJSON形式に整形する。
    ★★★ 集約キー: 担当者名(日), 科目名(日), 学期, 分野(日), 単位(日) ★★★
    複数年度ある場合は、最新年度のデータを基本とし、year と available_years を更新する。
    """
    if not all_raw_data: return []
    grouped_by_key = {}
    skipped_count = 0
    for item in all_raw_data:
        # --- ★★★ 集約キーに使用する値を取得 ★★★ ---
        # course_id はキーには使わないが、データ欠落チェックは get_syllabus_details で実施済み
        course_id = item.get('course_id') # course_id自体は最終出力に必要

        # 担当者名 (日本語、タプル化)
        professor_ja_key = item.get('professor_ja', '')
        professors_tuple = tuple(sorted([p.strip() for p in professor_ja_key.split('/') if p.strip()]))

        # 科目名 (日本語)
        name_ja_key = item.get('name_ja', '') # get_syllabus_details で追加したキー

        # 学期 (英語優先、小文字化されたもの)
        semester_agg_key = item.get('semester', 'unknown')
        semester_agg_key = semester_agg_key.lower()
        if semester_agg_key in ["学期不明", "不明"]: semester_agg_key = "unknown"

        # 分野 (日本語)
        field_ja_key = item.get('field_ja', '') # get_syllabus_details で追加したキー

        # 単位 (日本語)
        credits_ja_key = item.get('credits_ja', '') # get_syllabus_details で追加したキー

        # --- ★★★ 新しい集約キーを作成 ★★★ ---
        agg_key = (
            professors_tuple,
            name_ja_key,
            semester_agg_key,
            field_ja_key,
            credits_ja_key
        )

        # --- データが存在しないキー要素があればスキップ ---
        # (科目名、分野、単位は必須チェック済みのはずだが念のため)
        if not name_ja_key or not field_ja_key or not credits_ja_key:
            print(f"[警告] 集約キーに必要な情報が不足しています (Course ID: {course_id}, Year: {item.get('year_scraped')})。スキップします。")
            skipped_count += 1
            continue

        # 集約辞書にデータを追加
        if agg_key not in grouped_by_key: grouped_by_key[agg_key] = []
        grouped_by_key[agg_key].append(item)

    if skipped_count > 0: print(f"キー情報不足により {skipped_count} 件のデータが集約からスキップされました。")

    final_list = []
    for agg_key, year_data_list in grouped_by_key.items():
        # ★★★ 同じキーのデータは年度(year_scraped)で降順ソート (最新年度を先頭に) ★★★
        year_data_list.sort(key=lambda x: x['year_scraped'], reverse=True)
        # ★★★ 最新年度のデータを代表として使用 ★★★
        latest_data = year_data_list[0]
        # スクレイピングされた全年度をリストアップ (整数から文字列へ、降順)
        years_scraped_int = sorted(list(set(d['year_scraped'] for d in year_data_list)), reverse=True)
        available_years_str = [str(y) for y in years_scraped_int]

        # --- ★★★ 指定されたJSON形式に合わせてデータを構築 (最新年度データを使用) ★★★ ---
        trans_ja = latest_data.get('translations', {}).get('ja', {})
        trans_en = latest_data.get('translations', {}).get('en', {})

        # 学期情報 (最新年度のデータから取得し、英語優先・小文字化)
        semester_en = trans_en.get('semester', '')
        semester_ja = trans_ja.get('semester', 'unknown')
        semester_combined = semester_en if semester_en else semester_ja
        semester_final = semester_combined.lower()
        if semester_final in ["学期不明", "不明"]: semester_final = "unknown"

        # professors リストを作成 (最新年度のデータを使用)
        professors_list = []
        prof_ja_raw = trans_ja.get('professor', '')
        prof_en_raw = trans_en.get('professor', '')
        # department には field の値を使用 (最新年度)
        dept_ja = trans_ja.get('field', '')
        dept_en = trans_en.get('field', '')

        prof_ja_names = [name.strip() for name in prof_ja_raw.split('/') if name.strip()] if prof_ja_raw else []
        prof_en_names = [name.strip() for name in prof_en_raw.split('/') if name.strip()] if prof_en_raw else []

        max_len = max(len(prof_ja_names), len(prof_en_names))
        for i in range(max_len):
            prof_obj = {
                "name": {
                    "ja": prof_ja_names[i] if i < len(prof_ja_names) else "",
                    "en": prof_en_names[i] if i < len(prof_en_names) else ""
                },
                "department": {
                    "ja": dept_ja,
                    "en": dept_en
                }
            }
            if prof_obj["name"]["ja"] or prof_obj["name"]["en"]:
                professors_list.append(prof_obj)

        # 最終的なアイテムを作成
        aggregated_item = {
            "course_id": latest_data['course_id'], # トップレベルには course_id を含める
            "year": "&".join(available_years_str), # ★★★ 全年度を&区切り ★★★
            "semester": semester_final,
            "translations": {
                "ja": {
                    # ★★★ 指定されたキーのみ選択 (最新年度データ) ★★★
                    "name": trans_ja.get('name', ''),
                    "field": trans_ja.get('field', ''),
                    "credits": trans_ja.get('credits', ''),
                    "semester": trans_ja.get('semester', ''), # 日本語の学期
                    "Classroom": trans_ja.get('location', ''), # ★★★ 教室情報を追加 (キー名変更) ★★★
                    # ★★★ 必要に応じて追加 (例のフォーマットにはない) ★★★
                    # "day_period": trans_ja.get('day_period', ''),
                    # "selection_method": trans_ja.get('selection_method', ''),
                },
                "en": {
                    # ★★★ 指定されたキーのみ選択 (最新年度データ) ★★★
                    "name": trans_en.get('name', ''),
                    "field": trans_en.get('field', ''),
                    "credits": trans_en.get('credits', ''),
                    "semester": semester_en.lower() if semester_en else '', # 英語の学期 (小文字)
                    "Classroom": trans_en.get('location', ''), # ★★★ 教室情報を追加 (キー名変更) ★★★
                    # ★★★ 必要に応じて追加 (例のフォーマットにはない) ★★★
                    # "day_period": trans_en.get('day_period', ''),
                    # "selection_method": trans_en.get('selection_method', ''),
                }
            },
            "professors": professors_list,
            "available_years": available_years_str # ★★★ 全年度リスト ★★★
        }
        final_list.append(aggregated_item)
    return final_list

# --- login 関数 (変更なし) ---
def login(driver, email, password, screenshots_dir):
    """指定された情報でログイン処理を行う"""
    login_url = 'https://gslbs.keio.jp/syllabus/search' # ログイン開始URL
    max_login_attempts = 2 # 最大試行回数
    for attempt in range(max_login_attempts):
        print(f"\nログイン試行 {attempt + 1}/{max_login_attempts}...")
        try:
            driver.get(login_url) # ログインページへ移動
            # メールアドレス入力フィールドが表示されるまで待機
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @name='identifier']")))
            time.sleep(SHORT_WAIT) # 描画待機

            # メールアドレス入力
            username_field = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='email' or @name='identifier']")))
            username_field.clear(); username_field.send_keys(email); time.sleep(0.5)

            # 「次へ」ボタンをクリック (複数のセレクタを試す)
            next_button_selectors = ["//button[contains(., 'Next')]", "//button[contains(., '次へ')]", "//button[@type='submit']", "//input[@type='submit' and (contains(@value, 'Next') or contains(@value, '次へ'))]", "//div[@role='button' and (contains(., 'Next') or contains(., '次へ'))]" ]
            next_button = None
            for selector in next_button_selectors:
                try:
                    next_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if click_element(driver, next_button): break # クリック成功したらループ脱出
                    else: next_button = None # click_elementがFalseを返した場合
                except TimeoutException: continue # 見つからなければ次のセレクタへ
                except StaleElementReferenceException: time.sleep(1); continue # 要素が古くなったら少し待ってリトライ
                except (InvalidSessionIdException, NoSuchWindowException) as e_session: raise e_session # 致命的エラー

            # ボタンが見つからなかった場合、Enterキー送信を試す
            if not next_button:
                try: username_field.send_keys(Keys.RETURN)
                except Exception as e_enter: print(f"   Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_next_button_error_{attempt+1}", screenshots_dir); raise Exception("「次へ」ボタン処理失敗")

            # パスワード入力フィールドが表示されるまで待機
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            time.sleep(SHORT_WAIT)

            # パスワード入力
            password_field = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            password_field.clear(); password_field.send_keys(password); time.sleep(0.5)

            # 「サインイン」ボタンをクリック (複数のセレクタを試す)
            signin_button_selectors = ["//button[contains(., 'Sign in')]", "//button[contains(., 'サインイン')]", "//button[contains(., 'Verify')]", "//button[@type='submit']", "//input[@type='submit' and (contains(@value, 'Sign in') or contains(@value, 'サインイン') or contains(@value, 'Verify'))]", "//div[@role='button' and (contains(., 'Sign in') or contains(., 'サインイン') or contains(., 'Verify'))]" ]
            signin_button = None
            for selector in signin_button_selectors:
                try:
                    signin_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if click_element(driver, signin_button): break
                    else: signin_button = None
                except TimeoutException: continue
                except StaleElementReferenceException: time.sleep(1); continue
                except (InvalidSessionIdException, NoSuchWindowException) as e_session: raise e_session

            # ボタンが見つからなかった場合、Enterキー送信を試す
            if not signin_button:
                try: password_field.send_keys(Keys.RETURN)
                except Exception as e_enter: print(f"   Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_signin_button_error_{attempt+1}", screenshots_dir); raise Exception("「サインイン」ボタン処理失敗")

            # ログイン後の検索ページURLまたは検索ボタンが表示されるまで待機
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT + LONG_WAIT).until(EC.any_of(
                EC.url_contains("gslbs.keio.jp/syllabus/search"),
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '検索')]"))
            ))

            current_url = driver.current_url
            # ログイン成功判定
            if "gslbs.keio.jp/syllabus/search" in current_url:
                print("ログイン成功、検索ページに到達しました。")
                try:
                    # 検索ボタンがクリック可能か念のため確認
                    WebDriverWait(driver, MEDIUM_WAIT).until(EC.element_to_be_clickable((By.XPATH, "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(),'検索')]")))
                except TimeoutException:
                    print("[警告] 検索画面の主要要素確認タイムアウト。")
                return True # ログイン成功
            else:
                # ログイン後のURLが期待と異なる場合
                print(f"[警告] ログイン後のURLが期待した検索ページではありません。 URL: {current_url}")
                save_screenshot(driver, f"login_unexpected_page_{attempt+1}", screenshots_dir)
                # 2段階認証画面の可能性をチェック
                if "auth" in current_url or "verify" in current_url or "duo" in current_url:
                    print("[情報] 2段階認証ページに遷移した可能性があります。")
                    raise Exception("2段階認証検出") # 2段階認証は自動化困難なため例外発生

        # --- ログイン試行中のエラーハンドリング ---
        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
            print(f"[エラー] ログイン処理中にセッション/ウィンドウエラー (試行 {attempt + 1}): {e_session}")
            raise # 致命的エラー
        except TimeoutException as e:
            print(f"[エラー] ログイン処理中にタイムアウト (試行 {attempt + 1})。")
            save_screenshot(driver, f"login_timeout_{attempt+1}", screenshots_dir)
            if attempt == max_login_attempts - 1: raise e # 最終試行で raise
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)
        except WebDriverException as e:
            print(f"[エラー] ログイン処理中にWebDriverエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_webdriver_error_{attempt+1}", screenshots_dir)
            if "net::ERR" in str(e) or "connection reset" in str(e).lower(): # ネットワークエラーの可能性
                print("   ネットワーク接続またはURLの問題、またはリモートホストによる切断の可能性があります。")
            # 最終試行なら例外を再発生させて処理中断
            if attempt == max_login_attempts - 1:
                raise e
            # 最終試行でなければリトライメッセージを表示して待機
            print("リトライします...")
            time.sleep(MEDIUM_WAIT) # リトライ前に待機
        except Exception as e:
            print(f"[エラー] ログイン処理中に予期せぬエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_unknown_error_{attempt+1}", screenshots_dir)
            traceback.print_exc()
            if attempt == max_login_attempts - 1: raise e # 最終試行で raise
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)

    # ループを抜けた場合（通常は発生しないはずだが念のため）
    print("ログインに失敗しました。")
    return False


# --- check_session_timeout 関数 (変更なし) ---
def check_session_timeout(driver, screenshots_dir):
    """セッションタイムアウトページが表示されているか確認する"""
    try:
        current_url = driver.current_url # 現在のURL
        page_title = driver.title # ページのタイトル
        page_source = driver.page_source.lower() # ページソース（小文字化）

        # タイムアウトを示すキーワード
        timeout_keywords = ["セッションタイムアウト", "session timeout", "ログインし直してください", "log back in"]
        # エラーページのURLの一部
        error_page_url_part = "/syllabus/appMsg"

        is_session_timeout = False
        # URLがエラーページのものか
        if error_page_url_part in current_url: is_session_timeout = True
        # ページソースにタイムアウトキーワードが含まれるか
        elif any(keyword in page_source for keyword in timeout_keywords): is_session_timeout = True
        # タイトルに "error" が含まれ、かつソースにキーワードが含まれるか
        elif "error" in page_title.lower() and any(keyword in page_source for keyword in timeout_keywords): is_session_timeout = True

        if is_session_timeout:
            print("[警告] セッションタイムアウトページが検出されました。")
            save_screenshot(driver, "session_timeout_detected", screenshots_dir)
            return True # タイムアウト検出
        else:
            return False # タイムアウトではない

    except (TimeoutException, StaleElementReferenceException):
        # 要素アクセス中にタイムアウトやStaleになった場合は、タイムアウトではないと判断
        return False
    except WebDriverException as e:
        # WebDriver関連のエラー
        if "invalid session id" in str(e).lower() or "no such window" in str(e).lower():
            # セッションID無効やウィンドウ消失は致命的なので上位に伝播
            raise
        else:
            # その他のWebDriverエラーは警告としてログ出力
            print(f"[エラー] セッションタイムアウトチェック中に予期せぬWebDriverエラー: {e}")
            save_screenshot(driver, "session_check_webdriver_error", screenshots_dir)
            return False
    except Exception as e:
        # その他の予期せぬエラー
        print(f"[エラー] セッションタイムアウトチェック中に予期せぬエラー: {e}")
        save_screenshot(driver, "session_check_unknown_error", screenshots_dir)
        traceback.print_exc()
        return False

# --- initialize_driver 関数 (変更なし) ---
def initialize_driver(driver_path, headless=False):
    """WebDriver (Chrome) を初期化する"""
    print("\nWebDriverを初期化しています...")
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'normal' # ページの読み込み戦略 (normal, eager, none)

    # ヘッドレスモード設定
    if headless:
        options.add_argument('--headless')
        options.add_argument('--disable-gpu') # GPU無効化 (ヘッドレスで推奨)
        options.add_argument('--window-size=1920,1080') # ウィンドウサイズ指定
        print("ヘッドレスモードで実行します。")

    # 一般的なオプション (安定性向上、自動化検出回避など)
    options.add_argument('--disable-extensions') # 拡張機能無効化
    options.add_argument('--no-sandbox') # Sandbox無効化 (Linux等で必要になる場合あり)
    options.add_argument('--disable-dev-shm-usage') # /dev/shm使用制限回避 (Linux等)
    options.add_argument('--disable-infobars') # 「Chromeは自動テストソフトウェアによって制御されています」バー非表示
    options.add_argument('--disable-blink-features=AutomationControlled') # 自動化検出フラグ回避

    # 実験的なオプション (自動化検出回避)
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    new_driver = None
    try:
        # ChromeDriverのパスが指定され、存在する場合
        if driver_path and os.path.exists(driver_path):
            service = Service(executable_path=driver_path)
            new_driver = webdriver.Chrome(service=service, options=options)
        else:
            # パス未指定/無効の場合は自動検出を試みる (selenium-manager)
            print("ChromeDriverパス未指定/無効のため、自動検出します。")
            new_driver = webdriver.Chrome(options=options)

        # タイムアウト設定
        new_driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT) # ページ読み込みタイムアウト
        new_driver.implicitly_wait(5) # 暗黙的な待機 (要素が見つかるまでの最大待機時間)

        print("WebDriverの初期化完了。")
        return new_driver
    except WebDriverException as e:
        # WebDriver初期化時のエラー
        print(f"[重大エラー] WebDriverの初期化失敗: {e}")
        error_message = str(e).lower()
        # 一般的な原因と対策を表示
        if "session not created" in error_message:
            print("   原因: ChromeDriver と Chrome のバージョン不一致。対策: バージョンを確認し、対応するChromeDriverをDL/指定してください。")
        elif "executable needs to be in path" in error_message:
            print("   原因: ChromeDriver がPATH上にないか指定が誤り。対策: PATHを通すか、CHROME_DRIVER_PATHで指定してください。")
        else:
            traceback.print_exc() # その他のエラーはトレースバック表示
        return None
    except Exception as e:
        # その他の予期せぬエラー
        print(f"[重大エラー] WebDriver初期化中に予期せぬエラー: {e}")
        traceback.print_exc()
        return None


# --- ★★★ メイン処理 (ループ順序変更) ★★★ ---
if __name__ == "__main__":
    # 出力ディレクトリ作成、開始時間記録、変数初期化
    output_dir, logs_dir, screenshots_dir = create_output_dirs(OUTPUT_DIR_NAME)
    start_time_dt = datetime.datetime.now()
    output_json_path = os.path.join(output_dir, OUTPUT_JSON_FILE)
    driver = None
    scraped_data_all_years = [] # 全ての年度・分野の生データを格納するリスト
    global_start_time = time.time() # 全体の処理時間計測用
    print(f"スクレイピング開始: {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    # WebDriver初期化と初回ログイン
    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
    if not driver:
        sys.exit("致命的エラー: WebDriverを初期化できませんでした。") # 初期化失敗時は終了
    try:
        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
            sys.exit("致命的エラー: 初期ログインに失敗しました。") # 初回ログイン失敗時は終了
    except Exception as initial_login_e:
         # ログイン中の予期せぬエラー
        print(f"致命的エラー: 初期ログイン中に予期せぬ例外が発生: {initial_login_e}")
        traceback.print_exc()
        if driver:
            try:
                save_screenshot(driver, "initial_login_fatal_error", screenshots_dir)
                driver.quit() # ブラウザを閉じる試行
            except Exception as qe:
                print(f"初期ログインエラー後のブラウザ終了時エラー: {qe}")
        sys.exit(1) # エラー終了

    # --- ★★★ メインループ (年度 -> 分野 -> ページ -> 詳細) ★★★ ---
    try: # メインループ全体をtryで囲む
        # ★★★ 年度ループを外側に ★★★
        year_index = 0
        while year_index < len(TARGET_YEARS):
            year = TARGET_YEARS[year_index]
            print(f"\n<<<<< {year}年度 の処理開始 >>>>>")
            year_processed_successfully = True # 年度全体の処理成功フラグ

            # ★★★ 分野ループを内側に ★★★
            field_index = 0
            while field_index < len(TARGET_FIELDS):
                field_name = TARGET_FIELDS[field_index]
                print(f"\n===== 分野: {field_name} ({year}年度) の処理開始 =====")
                field_processed_successfully = True # 分野ごとの処理成功フラグ
                opened_links_this_year_field = set() # この年度・分野で処理済みの詳細ページURL記録用

                try: # 分野ごとの処理をtryで囲む

                    # --- セッションチェック＆再ログイン (分野ループ開始時) ---
                    if check_session_timeout(driver, screenshots_dir):
                        print("セッションタイムアウト検出。再ログイン試行...")
                        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                            print("[エラー] 再ログイン失敗。この分野をスキップします。")
                            field_index += 1; continue # 次の分野へ

                    # --- 検索ページ確認・移動 ---
                    try:
                        current_url_check = driver.current_url
                        if "gslbs.keio.jp/syllabus/search" not in current_url_check:
                            print("検索ページ以外にいるため、検索ページに移動します。")
                            driver.get('https://gslbs.keio.jp/syllabus/search')
                            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search"))
                            time.sleep(MEDIUM_WAIT) # ページ遷移後の待機
                    except WebDriverException as e_url_check:
                        print(f"[警告] 現在のURL確認中にエラー: {e_url_check}。セッションエラーとして処理します。")
                        raise InvalidSessionIdException("URL check failed, likely closed window.") from e_url_check

                    # --- 年度選択 ---
                    year_select_xpath = "//select[@name='KEYWORD_TTBLYR']"
                    year_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, year_select_xpath)))
                    if not select_option_by_text(driver, year_select_element, str(year)):
                        print(f"     [警告] 年度 '{year}' の選択に失敗。この分野をスキップします。")
                        save_screenshot(driver, f"year_selection_failed_{year}_{field_name}", screenshots_dir)
                        field_index += 1; continue # 次の分野へ
                    print(f"   年度 '{year}' を選択しました。")
                    time.sleep(SHORT_WAIT)

                    # --- 分野選択 ---
                    field_select_xpath = "//select[@name='KEYWORD_FLD1CD']"
                    field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                    if not select_option_by_text(driver, field_select_element, field_name):
                        print(f"     [警告] 分野 '{field_name}' の選択に失敗。スキップします。")
                        save_screenshot(driver, f"field_selection_failed_{field_name}_{year}", screenshots_dir)
                        field_index += 1; continue # 次の分野へ
                    print(f"   分野 '{field_name}' を選択しました。")
                    time.sleep(SHORT_WAIT) # 選択後の待機


                    # --- 学年チェックボックス処理 ---
                    try:
                        cb_xpath = "//input[@name='KEYWORD_LVL' and @value='3']"
                        cb = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, cb_xpath)))
                        if cb.is_selected():
                            print("   学年「3年」のチェックを外します。")
                            if not click_element(driver, cb):
                                print("       [警告] 学年「3年」チェックボックス解除失敗。")
                            time.sleep(0.5)
                    except TimeoutException: pass
                    except Exception as e_cb: print(f"       学年チェックボックス処理エラー: {e_cb}")

                    # --- 検索実行 ---
                    search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(), '検索')]"
                    search_button = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                    print("   検索ボタンをクリックします...")
                    if not click_element(driver, search_button):
                        print("     [エラー] 検索ボタンクリック失敗。この分野をスキップします。")
                        save_screenshot(driver, f"search_button_click_failed_{year}_{field_name}", screenshots_dir)
                        field_index += 1; continue # 次の分野へ

                    # --- 結果表示待機 ---
                    result_indicator_xpath = "//a[contains(@class, 'syllabus-detail')] | //div[contains(text(), '該当するデータはありません')] | //ul[contains(@class, 'pagination')]" # ページネーションも待機対象に
                    print("   検索結果表示待機中...")
                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                    time.sleep(SHORT_WAIT)
                    print("   検索結果表示完了。")

                    # --- 該当なしチェック ---
                    try:
                        no_result_element = driver.find_element(By.XPATH, "//div[contains(text(), '該当するデータはありません')]")
                        if no_result_element.is_displayed():
                            print(f"   [情報] {year}年度、分野 '{field_name}' に該当データなし。")
                            field_index += 1; continue # 次の分野へ
                    except NoSuchElementException: pass

                    # --- ソート順変更 ---
                    try:
                        sort_xpath = "//select[@name='SEARCH_RESULT_NARABIJUN']"
                        sort_element = WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, sort_xpath)))
                        print("   ソート順を「科目名順」に変更試行...")
                        if not select_option_by_text(driver, sort_element, "科目名順"):
                            try:
                                Select(sort_element).select_by_value("2")
                                print("     ソート順を Value='2' で選択しました。")
                                time.sleep(SHORT_WAIT)
                            except Exception:
                                print(f"       [警告] Value='2'でのソート失敗。")
                                try:
                                    driver.execute_script("arguments[0].value = '2'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));")
                                    print("       JSでソート順 Value='2' を設定しました。")
                                    time.sleep(SHORT_WAIT)
                                except Exception as e_js: print(f"       [警告] JSでのソートも失敗: {e_js}")
                        else:
                            print("     ソート順を「科目名順」で選択しました。")
                            time.sleep(SHORT_WAIT)
                    except TimeoutException: pass
                    except Exception as e_sort: print(f"   [警告] ソート設定エラー: {e_sort}")

                    # --- ★★★ 修正: ページネーションループ (ページ番号優先) ★★★ ---
                    last_processed_page_num = 0 # この年度/分野で処理した最後のページ番号
                    while True: # ページネーションブロックを処理するループ
                        print(f"\n   --- ページネーションブロック処理開始 (最終処理ページ: {last_processed_page_num}) ---")
                        pagination_processed_in_block = False # このブロックで何らかの処理が行われたか
                        current_page_links_processed = set() # このブロック内で処理したページ番号

                        # --- 1. 現在表示されているページ番号リンクを取得 ---
                        page_number_elements_info = []
                        try:
                            # pagination要素全体を再検索してStale対策
                            pagination_container = WebDriverWait(driver, MEDIUM_WAIT).until(
                                EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]"))
                            )
                            # アクティブなページ番号を取得
                            try:
                                 active_page_element = pagination_container.find_element(By.XPATH, ".//li[contains(@class, 'active')]/span | .//li[contains(@class, 'active')]/a")
                                 current_active_page_num = int(normalize_text(active_page_element.text))
                                 print(f"     現在のアクティブページ: {current_active_page_num}")
                                 # 最初のページ(1)または「次へ」で遷移した直後のページを処理
                                 if current_active_page_num > last_processed_page_num and current_active_page_num not in current_page_links_processed:
                                     print(f"     ページ {current_active_page_num} を処理します...")
                                     # --- リンク取得と詳細処理 ---
                                     syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]"
                                     urls_on_page = []
                                     processed_count_on_page = 0
                                     try:
                                         WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, syllabus_link_xpath)))
                                         current_links = driver.find_elements(By.XPATH, syllabus_link_xpath)
                                         urls_on_page = [link.get_attribute("href") for link in current_links if link.get_attribute("href")]
                                         urls_on_page = [url.strip() for url in urls_on_page if url]
                                         print(f"     ページ {current_active_page_num} で {len(urls_on_page)} 件のリンクを取得。")

                                         main_window = driver.current_window_handle
                                         for index, syllabus_url in enumerate(urls_on_page):
                                             if syllabus_url in opened_links_this_year_field: continue
                                             print(f"\n       詳細処理 {index + 1}/{len(urls_on_page)}: {syllabus_url}")
                                             syllabus_details = None
                                             try:
                                                 if check_session_timeout(driver, screenshots_dir): raise InvalidSessionIdException("Session timeout before detail fetch")
                                                 initial_handles = set(driver.window_handles)
                                                 driver.execute_script(f"window.open('{syllabus_url}', '_blank');")
                                                 WebDriverWait(driver, MEDIUM_WAIT).until(lambda d: len(d.window_handles) == len(initial_handles) + 1)
                                                 new_handle = list(set(driver.window_handles) - initial_handles)[0]
                                                 driver.switch_to.window(new_handle)
                                                 time.sleep(SHORT_WAIT)
                                                 syllabus_details = get_syllabus_details(driver, year, screenshots_dir)
                                                 if syllabus_details:
                                                     scraped_data_all_years.append(syllabus_details)
                                                     opened_links_this_year_field.add(syllabus_url)
                                                     processed_count_on_page += 1
                                                 else:
                                                     print(f"       [警告] URL {syllabus_url} の詳細情報取得失敗。")
                                             except Exception as e_detail: raise e_detail # Propagate detail processing errors
                                             finally:
                                                 current_handle = driver.current_window_handle
                                                 if current_handle != main_window:
                                                     try: driver.close()
                                                     except Exception: pass
                                                 try:
                                                      if main_window in driver.window_handles: driver.switch_to.window(main_window)
                                                      else: raise NoSuchWindowException("Main window lost")
                                                 except Exception as e_switch: raise e_switch # Propagate switch errors
                                             time.sleep(0.5) # Wait a bit after closing tab and switching back

                                     except (TimeoutException, StaleElementReferenceException) as e_link:
                                         print(f"     [警告] ページ {current_active_page_num} のリンク取得/処理中にエラー: {e_link}")
                                     except (InvalidSessionIdException, NoSuchWindowException) as e_session_detail:
                                          print(f"     [エラー] 詳細処理中にセッション/ウィンドウエラー: {e_session_detail}")
                                          field_processed_successfully = False; year_processed_successfully = False; break # Exit inner link loop and outer pagination loop
                                     except Exception as e_detail_proc:
                                          print(f"     [エラー] ページ {current_active_page_num} の詳細処理中に予期せぬエラー: {e_detail_proc}")
                                          traceback.print_exc()
                                          field_processed_successfully = False; year_processed_successfully = False; break # Exit inner link loop and outer pagination loop
                                     # --- 詳細処理ループ終了 ---
                                     if not field_processed_successfully: break # Exit pagination loop if detail processing failed

                                     last_processed_page_num = current_active_page_num
                                     current_page_links_processed.add(current_active_page_num)
                                     pagination_processed_in_block = True

                            except (NoSuchElementException, ValueError) as e_active:
                                 print(f"     アクティブページ番号の取得に失敗: {e_active}")
                                 # If it's the first time (last_processed_page_num == 0), assume page 1
                                 if last_processed_page_num == 0:
                                     print("     最初のページ(1)として処理を試みます...")
                                     current_active_page_num = 1
                                     # --- リンク取得と詳細処理 (上記と同様のコードをここに展開) ---
                                     syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]"
                                     urls_on_page = []
                                     processed_count_on_page = 0
                                     try:
                                         WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, syllabus_link_xpath)))
                                         current_links = driver.find_elements(By.XPATH, syllabus_link_xpath)
                                         urls_on_page = [link.get_attribute("href") for link in current_links if link.get_attribute("href")]
                                         urls_on_page = [url.strip() for url in urls_on_page if url]
                                         print(f"     ページ {current_active_page_num} で {len(urls_on_page)} 件のリンクを取得。")

                                         main_window = driver.current_window_handle
                                         for index, syllabus_url in enumerate(urls_on_page):
                                             if syllabus_url in opened_links_this_year_field: continue
                                             print(f"\n       詳細処理 {index + 1}/{len(urls_on_page)}: {syllabus_url}")
                                             syllabus_details = None
                                             try:
                                                 if check_session_timeout(driver, screenshots_dir): raise InvalidSessionIdException("Session timeout before detail fetch")
                                                 initial_handles = set(driver.window_handles)
                                                 driver.execute_script(f"window.open('{syllabus_url}', '_blank');")
                                                 WebDriverWait(driver, MEDIUM_WAIT).until(lambda d: len(d.window_handles) == len(initial_handles) + 1)
                                                 new_handle = list(set(driver.window_handles) - initial_handles)[0]
                                                 driver.switch_to.window(new_handle)
                                                 time.sleep(SHORT_WAIT)
                                                 syllabus_details = get_syllabus_details(driver, year, screenshots_dir)
                                                 if syllabus_details:
                                                     scraped_data_all_years.append(syllabus_details)
                                                     opened_links_this_year_field.add(syllabus_url)
                                                     processed_count_on_page += 1
                                                 else:
                                                     print(f"       [警告] URL {syllabus_url} の詳細情報取得失敗。")
                                             except Exception as e_detail: raise e_detail # Propagate detail processing errors
                                             finally:
                                                 current_handle = driver.current_window_handle
                                                 if current_handle != main_window:
                                                     try: driver.close()
                                                     except Exception: pass
                                                 try:
                                                      if main_window in driver.window_handles: driver.switch_to.window(main_window)
                                                      else: raise NoSuchWindowException("Main window lost")
                                                 except Exception as e_switch: raise e_switch # Propagate switch errors
                                             time.sleep(0.5) # Wait a bit after closing tab and switching back

                                     except (TimeoutException, StaleElementReferenceException) as e_link:
                                         print(f"     [警告] ページ {current_active_page_num} のリンク取得/処理中にエラー: {e_link}")
                                     except (InvalidSessionIdException, NoSuchWindowException) as e_session_detail:
                                          print(f"     [エラー] 詳細処理中にセッション/ウィンドウエラー: {e_session_detail}")
                                          field_processed_successfully = False; year_processed_successfully = False; break # Exit inner link loop and outer pagination loop
                                     except Exception as e_detail_proc:
                                          print(f"     [エラー] ページ {current_active_page_num} の詳細処理中に予期せぬエラー: {e_detail_proc}")
                                          traceback.print_exc()
                                          field_processed_successfully = False; year_processed_successfully = False; break # Exit inner link loop and outer pagination loop
                                     # --- 詳細処理ループ終了 ---
                                     if not field_processed_successfully: break # Exit pagination loop if detail processing failed

                                     last_processed_page_num = current_active_page_num
                                     current_page_links_processed.add(current_active_page_num)
                                     pagination_processed_in_block = True
                                 else:
                                     # アクティブページ取得失敗かつ初回でない場合は処理中断
                                     print("     [エラー] アクティブページを特定できず、処理を続行できません。")
                                     field_processed_successfully = False; year_processed_successfully = False; break

                            # アクティブページ処理後、年度/分野処理失敗ならループ中断
                            if not field_processed_successfully: break

                            # クリック可能なページ番号リンクを取得 (アクティブと無効を除く数字リンク)
                            page_number_links_xpath = ".//li[not(contains(@class, 'active')) and not(contains(@class, 'disabled'))]/a[number(text()) = number(text())]"
                            page_number_elements = pagination_container.find_elements(By.XPATH, page_number_links_xpath)

                            for link_element in page_number_elements:
                                try:
                                    page_num_text = normalize_text(link_element.text)
                                    page_num = int(page_num_text)
                                    # まだ処理していないページ番号のみを対象
                                    if page_num > last_processed_page_num and page_num not in current_page_links_processed:
                                        page_number_elements_info.append((page_num, link_element))
                                except (ValueError, StaleElementReferenceException):
                                    continue # 数字でないか、要素が古くなった場合は無視

                        except (NoSuchElementException, TimeoutException) as e_paginate_find:
                            print(f"     [警告] ページネーション要素の取得に失敗: {e_paginate_find}。この分野の処理を終了します。")
                            break # ページネーションループを抜ける

                        # ページ番号順にソート
                        page_number_elements_info.sort(key=lambda x: x[0])

                        # --- 2. 取得したページ番号リンクを順番にクリックして処理 ---
                        for page_num, link_element in page_number_elements_info:
                            print(f"     ページ {page_num} への遷移を試みます...")
                            try:
                                # クリック直前に要素を再検索してStale対策
                                link_to_click = WebDriverWait(driver, SHORT_WAIT).until(
                                    EC.element_to_be_clickable((By.XPATH, f"//ul[contains(@class, 'pagination')]//li/a[text()='{page_num}']"))
                                )
                                if click_element(driver, link_to_click):
                                    print(f"     ページ {page_num} へ遷移。結果待機中...")
                                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                    time.sleep(MEDIUM_WAIT) # ページ内容とページネーションの描画を待つ
                                    print(f"     ページ {page_num} を処理します...")

                                    # --- リンク取得と詳細処理 ---
                                    syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]"
                                    urls_on_page = []
                                    processed_count_on_page = 0
                                    try:
                                        # リンクが表示されるまで少し待つ
                                        WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, syllabus_link_xpath)))
                                        current_links = driver.find_elements(By.XPATH, syllabus_link_xpath)
                                        urls_on_page = [link.get_attribute("href") for link in current_links if link.get_attribute("href")]
                                        urls_on_page = [url.strip() for url in urls_on_page if url]
                                        print(f"     ページ {page_num} で {len(urls_on_page)} 件のリンクを取得。")

                                        main_window = driver.current_window_handle
                                        for index, syllabus_url in enumerate(urls_on_page):
                                            if syllabus_url in opened_links_this_year_field: continue
                                            print(f"\n       詳細処理 {index + 1}/{len(urls_on_page)}: {syllabus_url}")
                                            syllabus_details = None
                                            try:
                                                if check_session_timeout(driver, screenshots_dir): raise InvalidSessionIdException("Session timeout before detail fetch")
                                                initial_handles = set(driver.window_handles)
                                                driver.execute_script(f"window.open('{syllabus_url}', '_blank');")
                                                WebDriverWait(driver, MEDIUM_WAIT).until(lambda d: len(d.window_handles) == len(initial_handles) + 1)
                                                new_handle = list(set(driver.window_handles) - initial_handles)[0]
                                                driver.switch_to.window(new_handle)
                                                time.sleep(SHORT_WAIT)
                                                syllabus_details = get_syllabus_details(driver, year, screenshots_dir)
                                                if syllabus_details:
                                                    scraped_data_all_years.append(syllabus_details)
                                                    opened_links_this_year_field.add(syllabus_url)
                                                    processed_count_on_page += 1
                                                else:
                                                    print(f"       [警告] URL {syllabus_url} の詳細情報取得失敗。")
                                            except Exception as e_detail: raise e_detail # Propagate detail processing errors
                                            finally:
                                                current_handle = driver.current_window_handle
                                                if current_handle != main_window:
                                                    try: driver.close()
                                                    except Exception: pass
                                                try:
                                                     if main_window in driver.window_handles: driver.switch_to.window(main_window)
                                                     else: raise NoSuchWindowException("Main window lost")
                                                except Exception as e_switch: raise e_switch # Propagate switch errors
                                            time.sleep(0.5) # Wait a bit after closing tab and switching back

                                    except (TimeoutException, StaleElementReferenceException) as e_link:
                                        print(f"     [警告] ページ {page_num} のリンク取得/処理中にエラー: {e_link}")
                                    except (InvalidSessionIdException, NoSuchWindowException) as e_session_detail:
                                         print(f"     [エラー] 詳細処理中にセッション/ウィンドウエラー: {e_session_detail}")
                                         field_processed_successfully = False; year_processed_successfully = False; break # Exit inner link loop and outer pagination loop
                                    except Exception as e_detail_proc:
                                         print(f"     [エラー] ページ {page_num} の詳細処理中に予期せぬエラー: {e_detail_proc}")
                                         traceback.print_exc()
                                         field_processed_successfully = False; year_processed_successfully = False; break # Exit inner link loop and outer pagination loop
                                    # --- 詳細処理ループ終了 ---
                                    if not field_processed_successfully: break # Exit pagination loop if detail processing failed

                                    last_processed_page_num = page_num
                                    current_page_links_processed.add(page_num)
                                    pagination_processed_in_block = True
                                else:
                                    print(f"     [警告] ページ {page_num} のクリックに失敗。このブロックの残りのページ処理をスキップします。")
                                    break # このブロックのページ番号処理を中断
                            except (TimeoutException, StaleElementReferenceException, NoSuchElementException) as e_click:
                                print(f"     [警告] ページ {page_num} の検索/クリック中にエラー: {e_click}。このブロックの残りのページ処理をスキップします。")
                                break # このブロックのページ番号処理を中断
                            except Exception as e_proc_outer:
                                 print(f"     [エラー] ページ {page_num} の処理中に予期せぬエラー: {e_proc_outer}")
                                 traceback.print_exc()
                                 field_processed_successfully = False; year_processed_successfully = False # 年度/分野処理失敗フラグ
                                 break # このブロックのページ番号処理を中断

                        # 年度/分野処理失敗ならページネーションループを抜ける
                        if not field_processed_successfully: break

                        # --- 3. 「次へ」ボタンの処理 ---
                        try:
                            next_xpath = "//ul[contains(@class, 'pagination')]//li[not(contains(@class, 'disabled'))]/a[contains(text(), '次') or contains(., 'Next')]"
                            next_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, next_xpath)))
                            print(f"\n     ページ番号 {last_processed_page_num} まで処理完了。「次へ」をクリックします...")
                            if click_element(driver, next_button):
                                print("     「次へ」をクリックしました。結果待機中...")
                                WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                time.sleep(MEDIUM_WAIT) # ページ内容とページネーションの再描画を待つ
                                pagination_processed_in_block = True
                                # last_processed_page_num は次のループの開始時にアクティブページから更新される
                                continue # 次のページネーションブロックへ
                            else:
                                print("     [警告] 「次へ」ボタンのクリックに失敗。ページネーションを終了します。")
                                break # ページネーションループ終了
                        except TimeoutException:
                            print(f"\n     ページ番号 {last_processed_page_num} まで処理完了。「次へ」ボタンが見つからないか無効です。ページネーションを終了します。")
                            break # ページネーションループ終了
                        except Exception as e_next:
                            print(f"     [エラー] 「次へ」ボタンの検索/クリック中にエラー: {e_next}。ページネーションを終了します。")
                            break # ページネーションループ終了

                    # --- ページネーションループ終了 ---
                    if not field_processed_successfully:
                         print(f"--- 分野 {field_name} ({year}年度) 処理中にエラーが発生したため中断 ---")
                         # ここで break すると分野ループが中断され、次の分野へ進む


                # --- 分野ループの try...except...else ---
                except (InvalidSessionIdException, NoSuchWindowException) as e_session_field:
                    # 分野ループ中にセッション/ウィンドウエラーが発生した場合
                    print(f"\n[!!!] 分野 '{field_name}' ({year}年度) 処理中セッション/ウィンドウエラー: {e_session_field}。WebDriver再起動試行。")
                    if driver:
                        try: driver.quit()
                        except Exception as quit_err: print(f" WebDriver終了エラー: {quit_err}")
                    driver = None # quit試行後、driverをNoneに設定
                    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                    if not driver: raise Exception("WebDriver再初期化失敗。")
                    if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir): raise Exception("再ログイン失敗。")
                    print(f" WebDriver再起動・再ログイン完了。分野 '{field_name}' ({year}年度) 再試行。")
                    continue # field_index変えず再試行
                except Exception as e_field_main:
                     # その他の分野ループ中のエラー
                    print(f"   [エラー] 分野 '{field_name}' ({year}年度) 処理中エラー: {e_field_main}")
                    traceback.print_exc()
                    print(" この分野をスキップします。")
                    field_processed_successfully = False # この分野は失敗
                    year_processed_successfully = False # この年度も失敗扱いとする
                    # field_index += 1 # エラーでも次の分野へ進む
                finally:
                    # 分野処理が失敗した場合でも次の分野へ進む
                    if not field_processed_successfully:
                         print(f"===== 分野: {field_name} ({year}年度) 処理中断 =====")
                    else:
                         print(f"===== 分野: {field_name} ({year}年度) 正常終了 =====")
                    field_index += 1
            # --- 分野ループ終了 ---

            # 年度全体の処理が成功したかどうかにかかわらず、次の年度へ
            if not year_processed_successfully:
                 print(f"<<<<< {year}年度 の処理中にエラーがありましたが、次の年度へ進みます >>>>>")
            else:
                 print(f"<<<<< {year}年度 の処理正常終了 >>>>>")
            year_index += 1
        # --- 年度ループ終了 ---


    # --- グローバル try/except/finally ---
    except KeyboardInterrupt:
        print("\nキーボード割り込みにより処理中断。")
    except SystemExit as e:
        print(f"\nスクリプト停止 (終了コード: {e.code})。")
    except Exception as e_global:
        print(f"\n★★★ 重大エラー発生、処理中断: {e_global} ★★★")
        traceback.print_exc()
        if driver:
            print("重大エラー発生のため、スクリーンショットを試みます...")
            try:
                save_screenshot(driver, "fatal_error", screenshots_dir)
            except Exception:
                 print("[警告] エラー発生後のスクリーンショット保存に失敗しました。")
                 pass # Ignore errors during final screenshot attempt
    finally:
        # --- 終了処理 ---
        if driver:
            try:
                driver.quit()
                print("\nブラウザ終了。")
            except Exception as qe:
                print(f"\nブラウザ終了時エラー: {qe}")

        print("\n=== 最終処理 ===")
        if scraped_data_all_years:
            print(f"合計 {len(scraped_data_all_years)} 件の生データ取得。")
            print("\nデータ集約中...")
            final_json_data = aggregate_syllabus_data(scraped_data_all_years)
            if final_json_data:
                print(f"集約後データ件数: {len(final_json_data)}")
                print(f"\n'{output_json_path}' へ書き込み中...")
                try:
                    with open(output_json_path, mode='w', encoding='utf-8') as f:
                        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
                    print(f"JSON書き込み完了。")
                except Exception as e:
                    print(f"[エラー] JSON書き込みエラー: {e}")
            else:
                print("集約後データなし。JSON未作成。")
        else:
            print("\n有効データ収集されず。")

        end_time = time.time()
        elapsed_time = end_time - global_start_time
        print(f"\n処理時間: {elapsed_time:.2f} 秒")
        print(f"スクレイピング終了: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")