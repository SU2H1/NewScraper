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
# pprint をインポートしてターミナル出力を整形 (オプション)
# from pprint import pprint

# --- グローバル変数・設定 ---
CHROME_DRIVER_PATH = None # ChromeDriverのパス (Noneの場合は自動検出)
USER_EMAIL = 'kaitosumishi@keio.jp' # ログインに使用するメールアドレス
USER_PASSWORD = '0528QBSkaito' # ログインに使用するパスワード
OUTPUT_DIR_NAME = 'syllabus_output' # 出力ディレクトリ名
OUTPUT_JSON_FILE = 'syllabus_data.json' # 出力JSONファイル名
TARGET_FIELDS = ["基盤科目", "先端科目", "特設科目"] # スクレイピング対象の分野
TARGET_YEARS = [2025, 2024, 2023] # スクレイピング対象の年度
# ★★★ パフォーマンス向上のため、Trueに設定することを推奨 ★★★
HEADLESS_MODE = True # Trueにするとヘッドレスモードで実行
PAGE_LOAD_TIMEOUT = 45 # ページの読み込みタイムアウト時間(秒)
ELEMENT_WAIT_TIMEOUT = 60 # 要素が表示されるまでの最大待機時間(秒)
# ★★★ 待機時間を短縮して速度向上を試みる ★★★
SHORT_WAIT = 2 # 短い待機時間(秒) - 3から2へ変更
MEDIUM_WAIT = 3 # 中程度の待機時間(秒) - 5から3へ変更
LONG_WAIT = 5 # 長い待機時間(秒) - ログイン後など重要な箇所のため維持
# ★★★ 英語ページでのJSレンダリング待機時間 ★★★
JS_RENDER_WAIT = 2 # 秒 (必要に応じて調整) - 5から2へ変更

# --- ★ カスタム例外クラス ★ ---
class MissingCriticalDataError(Exception):
    """必須データまたは定義済みデータが取得できなかった場合に発生させる例外"""
    pass

# --- XPath定義 ---

# === 日本語ページ用 XPath ===
# ★★★ 2025年以降用 (日本語) ★★★
INFO_MAP_JA_2025 = {
    'name': ("科目名", "//h2[@class='class-name']", "名称不明"),
    'semester': ("学期", "//tr[th[normalize-space()='年度・学期']]/td", "学期不明"),
    'professor': ("担当者名", "//tr[th[contains(text(),'担当者名')]]/td", ""),
    'credits': ("単位", "//tr[th[contains(text(),'単位')]]/td", "単位不明"),
    'field': ("分野", "//tr[th[contains(text(),'分野')]]/td", "分野不明"),
    'location': ("教室", "//tr[th[contains(text(),'教室')]]/td", "教室不明"),
    'day_period': ("曜日時限", "//tr[th[contains(text(),'曜日時限')]]/td", "曜日時限不明"), # 曜日時限のXPath
    'selection_method': ("選抜方法", "//tr[th[contains(text(),'選抜方法')]]/td", ""), # 選抜方法のXPath
    'class_format': ("授業実施形態", "//tr[th[contains(text(),'授業実施形態')]]/td", ""),
    'course_id_fallback': ("登録番号(表)", "//tr[th[normalize-space()='登録番号']]/td", None)
}

# ★★★ 2023, 2024年用 (日本語) ★★★
INFO_MAP_JA_2023_2024 = {
    'name': ("科目名", "//h2/span[@class='title']", "名称不明"),
    'semester': ("学期", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='開講年度・学期']/following-sibling::dd[1]", "学期不明"),
    'professor': ("担当者名", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='授業教員名']/following-sibling::dd[1]", ""),
    'credits': ("単位", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='単位']/following-sibling::dd[1]", "単位不明"),
    'field': ("分野", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='分野']/following-sibling::dd[1]", "分野不明"),
    'location': ("教室", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='開講場所']/following-sibling::dd[1]", "教室不明"),
    'day_period': ("曜日時限", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='曜日・時限']/following-sibling::dd[1]", "曜日時限不明"), # 曜日時限のXPath
    'selection_method': ("選抜方法", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='選抜方法']/following-sibling::dd[1]", ""), # 選抜方法のXPath (仮、存在すれば)
    'class_format': ("授業実施形態", "//div[contains(@class,'syllabus-info')]//dl/dt[contains(text(),'実施形態')]/following-sibling::dd[1]", ""),
    'course_id_fallback': ("登録番号(表)", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='登録番号']/following-sibling::dd[1]", None)
}

# === ★★★ 英語ページ用 XPath (再定義) ★★★ ===
# ★★★ 2025年以降用 (英語) - ログのHTMLに基づいて修正 ★★★
INFO_MAP_EN_2025 = {
    'name': ("Course Title", "//h2[@class='class-name']", "Name Unknown"),
    'semester': ("Year/Semester", "//tr[th[normalize-space()='Academic Year/Semester']]/td", "Semester Unknown"),
    'professor': ("Lecturer(s)", "//tr[th[normalize-space()='Lecturer(s)']]/td", ""), # HTMLではLecturer(s)だった
    'credits': ("Credits", "//tr[th[normalize-space()='Credit(s)']]/td", "Credits Unknown"),
    'field': ("Field", "//tr[th[normalize-space()='Field']]/td", "Field Unknown"),
    'location': ("Classroom", "//tr[th[normalize-space()='Classroom']]/td", "Classroom Unknown"),
    'day_period': ("Day/Period", "//tr[th[normalize-space()='Day/Period']]/td", "Day/Period Unknown"), # 曜日時限のXPath (英)
    'selection_method': ("Selection Method", "//tr[th[normalize-space()='Lottery Method']]/td", ""), # 選抜方法のXPath (英)
    'class_format': ("Class Format", "//tr[th[normalize-space()='Class Format']]/td", ""),
    'course_id_fallback': ("Registration Number", "//tr[th[normalize-space()='Registration Number']]/td", None)
}

# ★★★ 2023, 2024年用 (英語) - 日本語版を元に推測 (要確認) ★★★
INFO_MAP_EN_2023_2024 = {
    'name': ("Course Title", "//h2/span[@class='title']", "Name Unknown"),
    'semester': ("Year/Semester", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Year/Semester']/following-sibling::dd[1]", "Semester Unknown"),
    'professor': ("Instructor(s)", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Instructor(s)']/following-sibling::dd[1]", ""), # 2025年と異なる可能性あり
    'credits': ("Credits", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Credits']/following-sibling::dd[1]", "Credits Unknown"),
    'field': ("Field", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Field']/following-sibling::dd[1]", "Field Unknown"),
    'location': ("Classroom", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Classroom']/following-sibling::dd[1]", "Classroom Unknown"), # 推測
    'day_period': ("Day/Period", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Day/Period']/following-sibling::dd[1]", "Day/Period Unknown"), # 曜日時限のXPath (英)
    'selection_method': ("Selection Method", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Selection Method']/following-sibling::dd[1]", ""), # 選抜方法のXPath (英, 仮)
    'class_format': ("Class Format", "//div[contains(@class,'syllabus-info')]//dl/dt[contains(text(),'Class Format')]/following-sibling::dd[1]", ""), # 推測
    'course_id_fallback': ("Registration No.", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Registration No.']/following-sibling::dd[1]", None) # 推測
}


# --- ヘルパー関数 ---

def create_output_dirs(base_dir=OUTPUT_DIR_NAME):
    """出力ディレクトリを作成する"""
    logs_dir = os.path.join(base_dir, "logs")
    screenshots_dir = os.path.join(base_dir, "screenshots")
    for dir_path in [base_dir, logs_dir, screenshots_dir]:
        os.makedirs(dir_path, exist_ok=True)
    return base_dir, logs_dir, screenshots_dir

def save_screenshot(driver, prefix="screenshot", dir_path="screenshots"):
    """スクリーンショットを保存する"""
    if not driver or not hasattr(driver, 'session_id') or driver.session_id is None:
        print("[警告] WebDriverが無効またはセッションIDがないため、スクリーンショットを保存できません。")
        return None
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(dir_path, filename)
        driver.save_screenshot(filepath)
        print(f"スクリーンショットを保存しました: {filepath}")
        return filepath
    except InvalidSessionIdException:
        print("[警告] スクリーンショット保存試行中にInvalidSessionIdExceptionが発生しました。")
        return None
    except WebDriverException as e:
        if "target window already closed" in str(e).lower():
            print("[警告] スクリーンショット保存試行中にウィンドウが閉じられました。")
        else:
            print(f"[エラー] スクリーンショットの保存に失敗: {e}")
        return None
    except Exception as e:
        print(f"[エラー] スクリーンショット保存中に予期せぬエラー: {e}")
        return None

def normalize_text(text):
    """テキストを正規化する (全角スペースを半角に、連続空白を1つに)"""
    if isinstance(text, str):
        text = text.replace('　', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    return ""

def click_element(driver, element, wait_time=SHORT_WAIT): # SHORT_WAITを使用
    """要素をクリックする (失敗時はJavaScriptで試行)"""
    try:
        WebDriverWait(driver, wait_time).until(EC.element_to_be_clickable(element))
        element.click()
        time.sleep(0.5) # クリック後の短い待機
        return True
    except ElementClickInterceptedException:
        try:
            # 要素が隠れている場合はスクロールしてからJSクリック
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.5)
            return True
        except Exception as js_e:
            print(f"           JavaScript Click中にエラー: {js_e}")
            return False
    except StaleElementReferenceException:
        print("           Click試行中に要素がStaleになりました。再取得が必要です。")
        return False
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        print(f"           Click中にセッション/ウィンドウエラー: {e_session}")
        raise # 致命的なエラーは再発生させる
    except Exception as e:
        print(f"           Click中に予期せぬエラー: {e}")
        return False

def select_option_by_text(driver, select_element, option_text, fallback_to_js=True):
    """Select要素のオプションをテキストで選択する (失敗時はJavaScriptで試行)"""
    try:
        select_obj = Select(select_element)
        select_obj.select_by_visible_text(option_text)
        time.sleep(0.3)
        # 選択が反映されたか確認
        selected_option = Select(select_element).first_selected_option
        if selected_option.text.strip() == option_text:
            return True
        else:
            # Seleniumでの選択が正しく反映されなかった場合
            raise Exception("Selection did not reflect correctly via Selenium.")
    except Exception as e:
        # Seleniumでの選択失敗時、JSフォールバック
        if fallback_to_js:
            print(f"           Seleniumでの'{option_text}'選択失敗({e})。JavaScriptで試行...")
            try:
                # JavaScriptでテキストが一致するオプションを選択し、change/inputイベントを発火
                js_script = f"""
                    let select = arguments[0]; let optionText = arguments[1];
                    for(let i = 0; i < select.options.length; i++) {{
                        if(select.options[i].text.trim() === optionText) {{
                            select.selectedIndex = i;
                            // イベントを発火させて変更を通知
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true; // 選択成功
                        }}
                    }}
                    return false; // 該当オプションなし
                """
                result = driver.execute_script(js_script, select_element, option_text)
                if result:
                    time.sleep(0.5) # JS実行後の待機
                    # JSで選択したテキストが正しいか確認
                    selected_option_text_js = driver.execute_script("return arguments[0].options[arguments[0].selectedIndex].text.trim();", select_element)
                    if selected_option_text_js == option_text:
                        print(f"           JavaScriptで'{option_text}'選択成功。")
                        return True
                    else:
                        print(f"           JavaScript選択後のテキスト不一致 (Expected: '{option_text}', Got: '{selected_option_text_js}')")
                        return False
                else:
                    print(f"           JavaScriptで'{option_text}'のオプションが見つかりませんでした。")
                    return False
            except (InvalidSessionIdException, NoSuchWindowException) as e_session:
                print(f"           JS選択中にセッション/ウィンドウエラー: {e_session}")
                raise # 致命的なエラー
            except Exception as js_error:
                print(f"           JavaScriptによる選択中にエラー: {js_error}")
                return False
        else:
            # JSフォールバックが無効な場合
            print(f"           Seleniumでの'{option_text}'選択失敗、JSフォールバック無効。")
            return False

def get_text_by_xpath(driver, xpath, default=""):
    """XPathで要素のテキストを取得する"""
    # XPathが空文字列の場合はデフォルト値を返す
    if not xpath:
        return default
    try:
        # ★★★ 要素待機時間をSHORT_WAITに変更 ★★★
        element = WebDriverWait(driver, SHORT_WAIT).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # 要素全体のテキストを取得し、正規化
        text_content = normalize_text(element.text)

        # もし取得したテキストがデフォルト値と同じなら、デフォルト値を返す
        # (デフォルト値が空文字の場合は、空でないテキストを採用)
        if default != "" and text_content == default:
             return default
        # それ以外（テキストが取得できた、またはデフォルトが空）の場合は取得テキストを返す
        return text_content if text_content else default

    except (TimeoutException, NoSuchElementException):
        # 要素が見つからない場合はデフォルト値を返す
        return default
    except StaleElementReferenceException:
        # 要素が古くなった場合
        print(f"     [警告] get_text_by_xpath: 要素がStaleになりました ({xpath})。デフォルト値「{default}」を使用。")
        return default
    except Exception as e:
        # その他の予期せぬエラー
        print(f"     [警告] get_text_by_xpath: 予期せぬエラー ({xpath}): {e}。デフォルト値「{default}」を使用。")
        return default

def generate_english_url(current_url):
    """現在のURLに lang=en パラメータを追加/置換して英語ページのURLを生成する"""
    try:
        parsed_url = urlparse(current_url)
        query_params = parse_qs(parsed_url.query)
        query_params['lang'] = ['en'] # langパラメータをenに設定（存在すれば上書き）
        new_query = urlencode(query_params, doseq=True) # クエリ文字列を再構築
        # 新しいクエリでURLを再構築
        english_url = urlunparse((
            parsed_url.scheme, parsed_url.netloc, parsed_url.path,
            parsed_url.params, new_query, parsed_url.fragment
        ))
        return english_url
    except Exception as e:
        print(f"     [警告] 英語URLの生成に失敗: {e}。元のURLを返します: {current_url}")
        return current_url

# --- ★★★ 追加: 学期抽出ヘルパー関数 ★★★ ---
def extract_season(semester_text):
    """学期文字列から季節 ("spring", "fall", "full year", "summer", "winter", "unknown") を抽出する"""
    if not isinstance(semester_text, str):
        return "unknown"

    text_lower = semester_text.lower()

    # 英語の季節を優先
    if "spring" in text_lower: return "spring"
    if "fall" in text_lower or "autumn" in text_lower: return "fall"
    if "summer" in text_lower: return "summer" # Summerも考慮
    if "winter" in text_lower: return "winter" # Winterも考慮
    if "full year" in text_lower or "通年" in semester_text: return "full year" # 通年も考慮

    # 日本語の季節
    if "春" in semester_text: return "spring"
    if "秋" in semester_text: return "fall"
    if "夏" in semester_text: return "summer"
    if "冬" in semester_text: return "winter"

    # どちらでもなければ不明
    return "unknown"


# --- ★★★ get_syllabus_details 関数の修正 ★★★ ---
def get_syllabus_details(driver, current_year, screenshots_dir):
    """
    シラバス詳細ページから指定された日本語と英語の情報を取得。
    日本語ページと英語ページを個別に処理し、それぞれの言語の情報を格納する。
    年度に応じて適切なXPathマップを使用する。
    ★★★ 修正: オンライン授業の場合、locationを強制的に上書き ★★★
    """
    ja_data = {} # 日本語ページから取得したデータ
    en_data = {} # 英語ページから取得したデータ
    course_id = None
    japanese_url = "N/A"

    # --- ★★★ 年度に応じて使用するXPathマップを選択 (日本語用) ★★★ ---
    if current_year >= 2025:
        ja_map_to_use = INFO_MAP_JA_2025
        print(f"        {current_year}年度のXPath定義(JA)を使用します。")
    else: # 2023, 2024年
        ja_map_to_use = INFO_MAP_JA_2023_2024
        print(f"        {current_year}年度のXPath定義(JA)を使用します。")

    # --- 1. 日本語ページの情報を取得 ---
    try:
        japanese_url = driver.current_url # 現在のURL (日本語版のはず)
        print(f"        日本語ページ処理中: {japanese_url}")
        # ★★★ 待機時間をMEDIUM_WAITに変更 ★★★
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(MEDIUM_WAIT) # 描画待機時間をMEDIUM_WAITに

        # --- Course ID 取得 (URL -> XPathフォールバック) ---
        print("           日本語 登録番号 取得試行...")
        try:
            id_match = re.search(r'[?&](?:id|entno)=(\d+)', japanese_url) or \
                       re.search(r'/courses/\d+_(\d+)', japanese_url) or \
                       re.search(r'/syllabus/(\d+)', japanese_url)
            if id_match:
                course_id = id_match.group(1)
            else:
                # ★★★ 日本語マップからフォールバックXPath取得 ★★★
                course_id_xpath = ja_map_to_use.get('course_id_fallback', [None, None])[1]
                if course_id_xpath:
                    print(f"           URLからID取得失敗。XPathで試行: {course_id_xpath}")
                    reg_num = get_text_by_xpath(driver, course_id_xpath)
                    if reg_num and reg_num.isdigit():
                        course_id = reg_num
                    else:
                        try:
                            hidden_elements = driver.find_elements(By.XPATH, "//input[@type='hidden' and (contains(@name, 'id') or contains(@name, 'entno'))]")
                            for hidden in hidden_elements:
                                value = hidden.get_attribute('value')
                                if value and value.isdigit():
                                    course_id = value
                                    print(f"           隠し要素からID取得: {value}")
                                    break
                        except Exception: pass
        except Exception as e:
            print(f"     [警告] Course ID の取得中にエラー: {e}")

        if not course_id:
            raise MissingCriticalDataError(f"必須データ(Course ID)の取得に失敗 (URL: {japanese_url})")
        print(f"           Course ID: {course_id}")

        # --- ★★★ 日本語情報取得ループ (日本語マップ使用) ★★★ ---
        name_default_ja = f"名称不明-{course_id}"
        # マップのデフォルト値を更新 (タプルの不変性のため再作成)
        name_tuple_ja = ja_map_to_use['name']
        ja_map_to_use['name'] = (name_tuple_ja[0], name_tuple_ja[1], name_default_ja)

        INVALID_COURSE_NAME_PATTERNS = ["慶應義塾大学 シラバス・時間割", "SFC Course Syllabus"]
        critical_data_missing = False
        missing_details = []

        print("        --- 日本語情報取得開始 ---")
        for key, (label, xpath, default_value, *_) in ja_map_to_use.items():
            if key == 'course_id_fallback': continue

            print(f"           日本語 {label} 取得試行 (XPath: {xpath if xpath else 'N/A'})...")
            ja_data[key] = get_text_by_xpath(driver, xpath, default_value) # ja_data に格納
            print(f"              -> {ja_data[key][:50]}...")

            # 必須チェック
            optional_keys = ['professor', 'selection_method', 'class_format'] # selection_methodもオプショナル扱い
            if key not in optional_keys:
                if key == 'name':
                    if ja_data[key] == default_value or any(pattern in ja_data[key] for pattern in INVALID_COURSE_NAME_PATTERNS):
                        critical_data_missing = True
                        missing_details.append(f"{label}(ja): 不適切「{ja_data[key]}」")
                elif ja_data[key] == default_value or not ja_data[key]:
                    if xpath: # XPathが定義されているのに取れなかった場合のみエラー
                        critical_data_missing = True
                        missing_details.append(f"{label}(ja): 未取得/空")

        # ★★★ 教室情報の上書きロジック (TTCK優先、次にオンライン) - 変更なし ★★★
        location_overwritten = False
        # 1. TTCKチェック
        if ja_data.get('name') and "TTCK" in ja_data['name']:
            print("           日本語: 科目名にTTCKが含まれるため、教室情報を「TTCK」に設定します。")
            ja_data['location'] = "TTCK"
            location_overwritten = True
        # 2. オンラインチェック (TTCKでなければ)
        elif ja_data.get('class_format') and "オンライン" in ja_data['class_format']:
             print("           日本語: オンライン授業のため、教室情報を「オンライン」に強制設定します。")
             ja_data['location'] = "オンライン"
             location_overwritten = True

        if location_overwritten:
             print(f"              -> 上書き後の教室(ja): {ja_data['location']}")

        # --- 必須データチェック ---
        if critical_data_missing:
            raise MissingCriticalDataError(f"必須日本語データ取得失敗 (URL: {japanese_url}): {'; '.join(missing_details)}")
        print("        --- 日本語情報取得完了 ---")

    # --- 日本語ページ取得エラーハンドリング ---
    except TimeoutException as e_timeout:
        print(f"     [エラー] 日本語ページ({japanese_url})の基本要素読み込みタイムアウト。スキップします。 {e_timeout}")
        save_screenshot(driver, f"detail_ja_load_timeout_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
        return None
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        print(f"     [エラー] 日本語ページ処理中にセッション/ウィンドウエラー: {e_session}")
        raise
    except MissingCriticalDataError as e_critical:
        print(f"     [エラー] {e_critical}")
        save_screenshot(driver, f"detail_ja_critical_missing_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
        raise # ★★★ 必須データ欠落は上位に伝播させる ★★★
    except Exception as e_ja:
        print(f"     [エラー] 日本語ページ({japanese_url})の処理中に予期せぬエラー: {e_ja}")
        save_screenshot(driver, f"detail_ja_unknown_error_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
        traceback.print_exc()
        return None # ★★★ 予期せぬエラーでもスキップ ★★★

    # --- 2. 英語ページの情報を取得 ---
    english_url = generate_english_url(japanese_url)
    print(f"        英語ページ処理中: {english_url}")
    try:
        driver.get(english_url)
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"        英語ページ読み込み完了。JavaScriptレンダリング待機中 ({JS_RENDER_WAIT}秒)...")
        time.sleep(JS_RENDER_WAIT) # ★★★ JSレンダリング待機時間をJS_RENDER_WAITに変更 ★★★
        print(f"        待機完了。英語情報取得試行...")

        # --- ★★★ 年度に応じて使用するXPathマップを選択 (英語用) ★★★ ---
        if current_year >= 2025:
            en_map_to_use = INFO_MAP_EN_2025
            print(f"        {current_year}年度のXPath定義(EN)を使用します。")
        else: # 2023, 2024年
            en_map_to_use = INFO_MAP_EN_2023_2024
            print(f"        {current_year}年度のXPath定義(EN)を使用します。")

        print("        --- 英語情報取得開始 ---")

        # --- ★★★ 英語情報取得ループ (英語マップ使用) ★★★ ---
        # en_data を初期化 (英語マップのデフォルト値で)
        en_data = {}
        name_default_en = f"Name Unknown-{course_id}"
        for key, (_, _, default_value_en, *_) in en_map_to_use.items():
             en_data[key] = default_value_en if key != 'name' else name_default_en

        # ★★★ 英語マップをループしてXPathを取得 ★★★
        for key, (label, xpath, default_value, *_) in en_map_to_use.items():
            if key == 'course_id_fallback': continue

            # ★★★ 英語ページで英語XPathを使って値を取得試行 ★★★
            print(f"           英語 {label} 取得試行 (XPath(EN): {xpath if xpath else 'N/A'})...")
            en_data[key] = get_text_by_xpath(driver, xpath, default_value) # default_valueも英語マップのものを使う
            print(f"              -> {en_data[key][:50]}...")

        # ★★★ 教室情報の上書きロジック (TTCK優先、次にオンライン) - 変更なし ★★★
        location_overwritten_en = False
        # 1. TTCKチェック
        if en_data.get('name') and "TTCK" in en_data['name']:
            print("           英語: 科目名にTTCKが含まれるため、教室情報を「TTCK」に設定します。")
            en_data['location'] = "TTCK" # 英語でもTTCKはそのまま
            location_overwritten_en = True
        # 2. オンラインチェック (TTCKでなければ)
        elif en_data.get('class_format') and ("online" in en_data['class_format'].lower() or "remote" in en_data['class_format'].lower()):
             print("           英語: オンライン授業のため、教室情報を「Online」に強制設定します。")
             en_data['location'] = "Online"
             location_overwritten_en = True

        if location_overwritten_en:
             print(f"              -> 上書き後の教室(en): {en_data['location']}")

        print("        --- 英語情報取得完了 ---")

    # --- 英語ページ取得エラーハンドリング (エラーでも続行) ---
    except TimeoutException as e_timeout_en:
        print(f"     [警告] 英語ページ({english_url})の読み込みタイムアウト。英語情報は一部欠落します。 {e_timeout_en}")
        save_screenshot(driver, f"detail_en_load_timeout_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        print(f"     [エラー] 英語ページ処理中にセッション/ウィンドウエラー: {e_session}")
        raise # 致命的エラーは再発生させる
    except Exception as e_en:
        print(f"     [警告] 英語ページ({english_url})の処理中に予期せぬエラー: {e_en}。英語情報は一部欠落します。")
        save_screenshot(driver, f"detail_en_unknown_error_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
        traceback.print_exc()
        # 英語ページのエラーは警告に留め、日本語データのみで続行できるように en_data を初期化（空またはデフォルト値）
        en_data = {} # エラー時は英語データを空にするか、デフォルト値にする

    # --- 3. 最終データ構築 ---
    final_details = {
        'course_id': course_id,
        'year_scraped': current_year,
        'translations': {
            'ja': {},
            'en': {}
        }
    }

    # ★★★ コピー対象キー (日本語マップ基準、course_id_fallback除く) ★★★
    # Note: We use JA map keys as the canonical set of fields to copy
    all_keys_to_copy = [k for k in ja_map_to_use.keys() if k != 'course_id_fallback']

    # 日本語データを translations['ja'] に格納
    for key in all_keys_to_copy:
        # class_format は最終出力に含めない (集約関数側で処理)
        final_details['translations']['ja'][key] = ja_data.get(key, "") # ja_data から取得

    # 英語データを translations['en'] に格納
    for key in all_keys_to_copy:
        # ★★★ en_data から取得。存在しないキーは空文字をデフォルトとする ★★★
        final_details['translations']['en'][key] = en_data.get(key, "")


    # --- トップレベルの semester, professor_ja, name_ja, field_ja, credits_ja を設定 (集約用) ---
    semester_en_raw = final_details['translations']['en'].get('semester', '')
    semester_ja_raw = final_details['translations']['ja'].get('semester', '')
    # 英語の季節を優先、なければ日本語の季節
    final_details['semester'] = extract_season(semester_en_raw) if extract_season(semester_en_raw) != "unknown" else extract_season(semester_ja_raw)
    final_details['professor_ja'] = final_details['translations']['ja'].get('professor', '')
    final_details['name_ja'] = final_details['translations']['ja'].get('name', '')
    final_details['field_ja'] = final_details['translations']['ja'].get('field', '')
    final_details['credits_ja'] = final_details['translations']['ja'].get('credits', '')

    # ★★★ ターミナルへの情報表示 (デバッグ用に選抜方法と曜日時限も追加) ★★★
    print("           --------------------------------------------------")
    print(f"           取得情報 (Course ID: {final_details['course_id']}, Year: {current_year}):")
    print(f"              科目名(ja): {final_details['translations']['ja'].get('name', 'N/A')}")
    print(f"              科目名(en): {final_details['translations']['en'].get('name', 'N/A')}")
    print(f"              学期(集約用): {final_details['semester']}") # 季節のみ表示
    print(f"              学期(ja): {final_details['translations']['ja'].get('semester', 'N/A')}") # 元の文字列
    print(f"              学期(en): {final_details['translations']['en'].get('semester', 'N/A')}") # 元の文字列
    print(f"              担当者(ja): {final_details['translations']['ja'].get('professor', 'N/A')}")
    print(f"              担当者(en): {final_details['translations']['en'].get('professor', 'N/A')}")
    print(f"              単位(ja): {final_details['translations']['ja'].get('credits', 'N/A')}")
    print(f"              単位(en): {final_details['translations']['en'].get('credits', 'N/A')}")
    print(f"              分野(ja): {final_details['translations']['ja'].get('field', 'N/A')}")
    print(f"              分野(en): {final_details['translations']['en'].get('field', 'N/A')}")
    print(f"              教室(ja): {final_details['translations']['ja'].get('location', 'N/A')}") # 上書きされている可能性あり
    print(f"              教室(en): {final_details['translations']['en'].get('location', 'N/A')}") # 上書きされている可能性あり
    print(f"              曜日時限(ja): {final_details['translations']['ja'].get('day_period', 'N/A')}")
    print(f"              曜日時限(en): {final_details['translations']['en'].get('day_period', 'N/A')}")
    print(f"              選抜方法(ja): {final_details['translations']['ja'].get('selection_method', 'N/A')}")
    print(f"              選抜方法(en): {final_details['translations']['en'].get('selection_method', 'N/A')}")
    print("           --------------------------------------------------")

    print(f"           ✓ 詳細情報取得完了: 「{final_details['translations']['ja'].get('name', '不明')}」 (Year: {current_year}, Semester: {final_details['semester']})")
    return final_details


# --- ★★★ aggregate_syllabus_data 関数の修正 ★★★ ---
def aggregate_syllabus_data(all_raw_data):
    """
    複数年度にわたる生データを集約し、指定されたJSON形式に整形する。
    ★★★ 集約キー: 担当者名(日), 科目名(日), 学期(季節のみ), 分野(日), 単位(日) ★★★ (登録番号を除外)
    複数年度ある場合は、最新年度のデータを基本とし、year と available_years を更新する。
    """
    if not all_raw_data: return []
    grouped_by_key = {}
    skipped_count = 0
    print("\n--- データ集約開始 ---")
    for item in all_raw_data:
        # --- ★★★ 集約キーに使用する値を取得 ★★★ ---
        course_id = item.get('course_id') # course_id は取得するが、キーには含めない

        # 担当者名 (日本語、タプル化)
        professor_ja_key = item.get('professor_ja', '')
        # '/' または ',' で分割し、ソートしてタプル化
        professors_tuple = tuple(sorted([p.strip() for p in re.split('[/,]', professor_ja_key) if p.strip()]))

        # 科目名 (日本語)
        name_ja_key = item.get('name_ja', '')

        # 学期 (get_syllabus_details で設定された 'semester' (季節のみのはず) を使用)
        semester_agg_key = item.get('semester', 'unknown')

        # 分野 (日本語)
        field_ja_key = item.get('field_ja', '')

        # 単位 (日本語)
        credits_ja_key = item.get('credits_ja', '')

        # --- ★★★ 新しい集約キーを作成 (登録番号を除外) ★★★ ---
        agg_key = (
            # course_id, # ★★★ 登録番号を除外 ★★★
            professors_tuple,
            name_ja_key,
            semester_agg_key, # 季節のみ
            field_ja_key,
            credits_ja_key
        )

        # --- データが存在しないキー要素があればスキップ ---
        # ★★★ course_id のチェックを除外 ★★★
        if not name_ja_key or not field_ja_key or not credits_ja_key or semester_agg_key == "unknown":
            print(f"[警告] 集約キーに必要な情報が不足または学期不明 (Course ID: {course_id}, Year: {item.get('year_scraped')}, Semester: {semester_agg_key})。スキップします。")
            skipped_count += 1
            continue

        # 集約辞書にデータを追加
        if agg_key not in grouped_by_key: grouped_by_key[agg_key] = []
        grouped_by_key[agg_key].append(item)

    if skipped_count > 0: print(f"キー情報不足または学期不明により {skipped_count} 件のデータが集約からスキップされました。")
    print(f"{len(grouped_by_key)} 件に集約されました。")

    final_list = []
    item_count = 0
    for agg_key, year_data_list in grouped_by_key.items():
        item_count += 1
        if item_count % 100 == 0:
             print(f"   集約処理中... {item_count}/{len(grouped_by_key)}")

        # ★★★ 同じキーのデータは年度(year_scraped)で降順ソート (最新年度を先頭に) ★★★
        year_data_list.sort(key=lambda x: x['year_scraped'], reverse=True)
        latest_data = year_data_list[0]
        years_scraped_int = sorted(list(set(d['year_scraped'] for d in year_data_list)), reverse=True)
        available_years_str = [str(y) for y in years_scraped_int]

        # --- ★★★ 指定されたJSON形式に合わせてデータを構築 (最新年度データを使用) ★★★ ---
        trans_ja = latest_data.get('translations', {}).get('ja', {})
        trans_en = latest_data.get('translations', {}).get('en', {})

        # 学期情報 (集約キーで使用した季節をそのまま使う)
        # agg_key = (prof_tuple, name, semester, field, credits) なのでインデックスがずれる
        semester_final = agg_key[2] # ★★★ インデックスを修正 (3 -> 2) ★★★

        # professors リストを作成 (変更なし)
        professors_list = []
        prof_ja_raw = trans_ja.get('professor', '')
        prof_en_raw = trans_en.get('professor', '')
        dept_ja = trans_ja.get('field', '')
        dept_en = trans_en.get('field', '') # 英語の分野も取得しておく

        prof_ja_names = [name.strip() for name in re.split('[/,]', prof_ja_raw) if name.strip()] if prof_ja_raw else []
        prof_en_names = [name.strip() for name in re.split('[/,]', prof_en_raw) if name.strip()] if prof_en_raw else []

        num_professors = len(prof_ja_names)
        prof_en_names.extend([""] * (num_professors - len(prof_en_names)))
        if len(prof_en_names) > num_professors:
            prof_en_names = prof_en_names[:num_professors]

        for i in range(num_professors):
            prof_obj = {
                "name": {
                    "ja": prof_ja_names[i],
                    "en": prof_en_names[i] if i < len(prof_en_names) and prof_en_names[i] else prof_ja_names[i] # Fallback to JA name if EN missing/empty
                },
                "department": {
                    "ja": dept_ja,
                    "en": dept_en # 英語の分野を使用
                }
            }
            professors_list.append(prof_obj)

        # 最終的なアイテムを作成
        aggregated_item = {
            # ★★★ course_id は最新のものを保持する (キーには使わない) ★★★
            "course_id": latest_data['course_id'],
            "year": "&".join(available_years_str),
            "semester": semester_final, # ★★★ 季節のみ ★★★
            "translations": {
                "ja": {
                    "name": trans_ja.get('name', ''),
                    "field": trans_ja.get('field', ''),
                    "credits": trans_ja.get('credits', ''),
                    "semester": trans_ja.get('semester', ''), # 元の日本語学期文字列 (年度含む可能性あり)
                    "Classroom": trans_ja.get('location', ''), # location は get_syllabus_details で上書きされている可能性あり
                    "day_period": trans_ja.get('day_period', ''),
                    "selection_method": trans_ja.get('selection_method', '')
                },
                "en": {
                    "name": trans_en.get('name', ''),
                    "field": trans_en.get('field', ''),
                    "credits": trans_en.get('credits', ''),
                    "semester": trans_en.get('semester', ''), # 元の英語学期文字列 (年度含む可能性あり)
                    "Classroom": trans_en.get('location', ''), # location は get_syllabus_details で上書きされている可能性あり
                    "day_period": trans_en.get('day_period', ''),
                    "selection_method": trans_en.get('selection_method', '')
                }
            },
            "professors": professors_list,
            "available_years": available_years_str
        }
        final_list.append(aggregated_item)
    print("--- データ集約完了 ---")
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
                try:
                    print("     「次へ」ボタンが見つからないため、Enterキーを送信します。")
                    username_field.send_keys(Keys.RETURN)
                    time.sleep(MEDIUM_WAIT) # Enter送信後の待機
                except Exception as e_enter: print(f"     Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_next_button_error_{attempt+1}", screenshots_dir); raise Exception("「次へ」ボタン処理失敗")

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
                try:
                    print("     「サインイン」ボタンが見つからないため、Enterキーを送信します。")
                    password_field.send_keys(Keys.RETURN)
                    time.sleep(LONG_WAIT) # Enter送信後の長めの待機
                except Exception as e_enter: print(f"     Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_signin_button_error_{attempt+1}", screenshots_dir); raise Exception("「サインイン」ボタン処理失敗")

            # ログイン後の検索ページURLまたは検索ボタンが表示されるまで待機
            print("     ログイン後のページ遷移待機中...")
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT + LONG_WAIT).until(EC.any_of(
                EC.url_contains("gslbs.keio.jp/syllabus/search"),
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '検索')] | //button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE']")) # 検索ボタンのセレクタも追加
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
                    # タイムアウトしてもURLが正しければ成功とみなす場合もある
                return True # ログイン成功
            else:
                # ログイン後のURLが期待と異なる場合
                print(f"[警告] ログイン後のURLが期待した検索ページではありません。 URL: {current_url}")
                save_screenshot(driver, f"login_unexpected_page_{attempt+1}", screenshots_dir)
                # 2段階認証画面の可能性をチェック
                if "auth" in current_url or "verify" in current_url or "duo" in current_url or "device" in current_url:
                    print("[情報] 2段階認証またはデバイス確認ページに遷移した可能性があります。")
                    raise Exception("2段階認証/デバイス確認検出") # 自動化困難なため例外発生
                # その他の予期せぬページ
                print("     予期せぬページに遷移しました。ログイン失敗と判断します。")
                # 失敗とみなし、リトライへ

        # --- ログイン試行中のエラーハンドリング ---
        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
            print(f"[エラー] ログイン処理中にセッション/ウィンドウエラー (試行 {attempt + 1}): {e_session}")
            raise # 致命的エラー
        except TimeoutException as e:
            print(f"[エラー] ログイン処理中にタイムアウト (試行 {attempt + 1})。")
            save_screenshot(driver, f"login_timeout_{attempt+1}", screenshots_dir)
            if attempt == max_login_attempts - 1: raise Exception("ログインタイムアウト") from e # 最終試行で raise
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)
        except WebDriverException as e:
            print(f"[エラー] ログイン処理中にWebDriverエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_webdriver_error_{attempt+1}", screenshots_dir)
            if "net::ERR" in str(e) or "connection reset" in str(e).lower(): # ネットワークエラーの可能性
                print("     ネットワーク接続またはURLの問題、またはリモートホストによる切断の可能性があります。")
            # 最終試行なら例外を再発生させて処理中断
            if attempt == max_login_attempts - 1:
                 raise Exception("ログイン中にWebDriverエラー") from e
            # 最終試行でなければリトライメッセージを表示して待機
            print("リトライします...")
            time.sleep(MEDIUM_WAIT) # リトライ前に待機
        except Exception as e:
            print(f"[エラー] ログイン処理中に予期せぬエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_unknown_error_{attempt+1}", screenshots_dir)
            traceback.print_exc()
            if attempt == max_login_attempts - 1: raise Exception("ログイン中に予期せぬエラー") from e # 最終試行で raise
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)

    # ループを抜けた場合（リトライ上限に達した場合）
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
            print(f"[エラー] セッションタイムアウトチェック中に致命的なWebDriverエラー: {e}")
            raise # ★★★ 致命的エラーは再発生させる ★★★
        else:
            # その他のWebDriverエラーは警告としてログ出力
            print(f"[エラー] セッションタイムアウトチェック中に予期せぬWebDriverエラー: {e}")
            save_screenshot(driver, "session_check_webdriver_error", screenshots_dir)
            return False # タイムアウトではないと判断
    except Exception as e:
        # その他の予期せぬエラー
        print(f"[エラー] セッションタイムアウトチェック中に予期せぬエラー: {e}")
        save_screenshot(driver, "session_check_unknown_error", screenshots_dir)
        traceback.print_exc()
        return False # タイムアウトではないと判断

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
    options.add_argument('--log-level=3') # ログレベルを警告以上のみに設定

    # 実験的なオプション (自動化検出回避)
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging']) # loggingも除外
    options.add_experimental_option('useAutomationExtension', False)

    new_driver = None
    try:
        # ChromeDriverのパスが指定され、存在する場合
        if driver_path and os.path.exists(driver_path):
            service = Service(executable_path=driver_path)
            new_driver = webdriver.Chrome(service=service, options=options)
            print(f"指定されたChromeDriverを使用: {driver_path}")
        else:
            # パス未指定/無効の場合は自動検出を試みる (selenium-manager)
            print("ChromeDriverパス未指定/無効のため、自動検出します。")
            service = Service() # 自動検出用サービス
            new_driver = webdriver.Chrome(service=service, options=options)
            print(f"自動検出されたChromeDriverを使用: {service.path}")


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
            print("     原因: ChromeDriver と Chrome のバージョン不一致の可能性。")
            print("     対策: Chromeを最新版に更新するか、Chromeのバージョンに合ったChromeDriverをダウンロードし、CHROME_DRIVER_PATHで指定してください。")
            print("     Chromeバージョン確認: chrome://version")
            print("     ChromeDriverダウンロード: https://chromedriver.chromium.org/downloads または https://googlechromelabs.github.io/chrome-for-testing/")
        elif "executable needs to be in path" in error_message:
            print("     原因: ChromeDriver がPATH上にないか指定が誤り。")
            print("     対策: ChromeDriverをダウンロードし、PATHを通すか、CHROME_DRIVER_PATHで指定してください。")
        elif "unable to discover open window in chrome" in error_message:
             print("     原因: Chromeブラウザの起動に失敗した可能性。")
             print("     対策: Chromeが正常にインストールされているか確認してください。")
        else:
             traceback.print_exc() # その他のエラーはトレースバック表示
        return None
    except Exception as e:
        # その他の予期せぬエラー
        print(f"[重大エラー] WebDriver初期化中に予期せぬエラー: {e}")
        traceback.print_exc()
        return None


# --- ★★★ JSONファイル書き込み関数 ★★★ ---
def write_json_data(data, path):
    """指定されたパスにJSONデータを書き込む"""
    print(f"\n'{path}' へ書き込み中 ({len(data)} 件)...")
    try:
        # 書き込む前にディレクトリが存在するか確認
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode='w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"JSON書き込み完了。")
    except Exception as e:
        print(f"[エラー] JSON書き込みエラー: {e}")

# --- ★★★ メイン処理 (変更なし) ★★★ ---
if __name__ == "__main__":
    # 出力ディレクトリ作成、開始時間記録、変数初期化
    output_dir, logs_dir, screenshots_dir = create_output_dirs(OUTPUT_DIR_NAME)
    start_time_dt = datetime.datetime.now()
    output_json_path = os.path.join(output_dir, OUTPUT_JSON_FILE)
    driver = None
    scraped_data_all_years = [] # 全ての年度・分野の生データを格納するリスト
    global_start_time = time.time() # 全体の処理時間計測用
    print(f"スクレイピング開始: {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象年度: {TARGET_YEARS}")
    print(f"対象分野: {TARGET_FIELDS}")
    print(f"出力先JSON: {output_json_path}")

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
                            time.sleep(MEDIUM_WAIT) # ★★★ ページ遷移後の待機時間をMEDIUM_WAITに ★★★
                    except WebDriverException as e_url_check:
                        # URL確認時のエラーはセッションエラーとして扱う
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
                    time.sleep(SHORT_WAIT) # ★★★ 選択後の待機時間をSHORT_WAITに ★★★

                    # --- 分野選択 ---
                    field_select_xpath = "//select[@name='KEYWORD_FLD1CD']"
                    field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                    if not select_option_by_text(driver, field_select_element, field_name):
                        print(f"     [警告] 分野 '{field_name}' の選択に失敗。スキップします。")
                        save_screenshot(driver, f"field_selection_failed_{field_name}_{year}", screenshots_dir)
                        field_index += 1; continue # 次の分野へ
                    print(f"   分野 '{field_name}' を選択しました。")
                    time.sleep(SHORT_WAIT) # ★★★ 選択後の待機時間をSHORT_WAITに ★★★


                    # --- 学年チェックボックス処理 (3年を解除) ---
                    try:
                        cb_xpath = "//input[@name='KEYWORD_LVL' and @value='3']"
                        cb = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, cb_xpath)))
                        if cb.is_selected():
                            print("   学年「3年」のチェックを外します。")
                            if not click_element(driver, cb):
                                 print("           [警告] 学年「3年」チェックボックス解除失敗。")
                            time.sleep(0.5) # チェック変更後の待機
                    except TimeoutException: pass # チェックボックスがない場合は無視
                    except Exception as e_cb: print(f"           学年チェックボックス処理エラー: {e_cb}")

                    # --- 検索実行 ---
                    search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(), '検索')]"
                    search_button = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                    print("   検索ボタンをクリックします...")
                    if not click_element(driver, search_button):
                        print("     [エラー] 検索ボタンクリック失敗。この分野をスキップします。")
                        save_screenshot(driver, f"search_button_click_failed_{year}_{field_name}", screenshots_dir)
                        field_index += 1; continue # 次の分野へ

                    # --- 結果表示待機 ---
                    # 結果リンク、"該当なし"メッセージ、またはページネーションが表示されるまで待つ
                    result_indicator_xpath = "//a[contains(@class, 'syllabus-detail')] | //div[contains(text(), '該当するデータはありません')] | //ul[contains(@class, 'pagination')]"
                    print("   検索結果表示待機中...")
                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                    time.sleep(MEDIUM_WAIT) # ★★★ 結果表示後の描画待機時間をMEDIUM_WAITに ★★★
                    print("   検索結果表示完了。")

                    # --- 該当なしチェック ---
                    try:
                        no_result_element = driver.find_element(By.XPATH, "//div[contains(text(), '該当するデータはありません')]")
                        if no_result_element.is_displayed():
                            print(f"   [情報] {year}年度、分野 '{field_name}' に該当データなし。")
                            field_index += 1; continue # 次の分野へ
                    except NoSuchElementException: pass # 該当なしメッセージがなければOK

                    # --- ソート順変更 (科目名順) ---
                    try:
                        sort_xpath = "//select[@name='SEARCH_RESULT_NARABIJUN']"
                        sort_element = WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, sort_xpath)))
                        current_sort_value = Select(sort_element).first_selected_option.get_attribute('value')
                        # すでに科目名順(value=2)でなければ変更
                        if current_sort_value != '2':
                            print("   ソート順を「科目名順」に変更試行...")
                            if not select_option_by_text(driver, sort_element, "科目名順"):
                                try:
                                    # テキストでの選択失敗時、valueで試行
                                    Select(sort_element).select_by_value("2")
                                    print("           ソート順を Value='2' で選択しました。")
                                    time.sleep(MEDIUM_WAIT) # ★★★ ソート変更後の待機時間をMEDIUM_WAITに ★★★
                                    # 結果表示を再度待機
                                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                    time.sleep(MEDIUM_WAIT) # ★★★ 再描画待機時間をMEDIUM_WAITに ★★★
                                except Exception as e_sort_val:
                                    print(f"           [警告] Value='2'でのソート失敗: {e_sort_val}。JSで試行...")
                                    try:
                                        driver.execute_script("arguments[0].value = '2'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", sort_element)
                                        print("           JSでソート順 Value='2' を設定しました。")
                                        time.sleep(MEDIUM_WAIT) # ★★★ JS実行後の待機時間をMEDIUM_WAITに ★★★
                                        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                        time.sleep(MEDIUM_WAIT) # ★★★ 再描画待機時間をMEDIUM_WAITに ★★★
                                    except Exception as e_js: print(f"           [警告] JSでのソートも失敗: {e_js}")
                            else:
                                print("           ソート順を「科目名順」で選択しました。")
                                time.sleep(MEDIUM_WAIT) # ★★★ ソート変更後の待機時間をMEDIUM_WAITに ★★★
                                WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                time.sleep(MEDIUM_WAIT) # ★★★ 再描画待機時間をMEDIUM_WAITに ★★★
                        else:
                             print("   ソート順は既に「科目名順」です。")

                    except TimeoutException: pass # ソート要素が見つからない場合は無視
                    except Exception as e_sort: print(f"   [警告] ソート設定エラー: {e_sort}")

                    # --- ★★★ ページネーションループ ★★★ ---
                    last_processed_page_num = 0 # この年度/分野で処理した最後のページ番号
                    while True: # ページネーションブロックを処理するループ
                        print(f"\n     --- ページネーションブロック処理開始 (最終処理ページ: {last_processed_page_num}) ---")
                        pagination_processed_in_block = False # このブロックで何らかの処理が行われたか
                        current_page_links_processed_in_block = set() # このブロック内で処理したページ番号

                        # --- 1. 現在表示されているページ番号リンクを取得 & アクティブページ処理 ---
                        current_active_page_num = -1
                        try:
                            # pagination要素全体を再検索してStale対策
                            pagination_container = WebDriverWait(driver, MEDIUM_WAIT).until(
                                EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]"))
                            )
                            # アクティブなページ番号を取得
                            try:
                                active_page_element = pagination_container.find_element(By.XPATH, ".//li[contains(@class, 'active')]/span | .//li[contains(@class, 'active')]/a")
                                current_active_page_num = int(normalize_text(active_page_element.text))
                                print(f"        現在のアクティブページ: {current_active_page_num}")
                            except (NoSuchElementException, ValueError) as e_active:
                                print(f"        アクティブページ番号の取得に失敗: {e_active}")
                                # 最初のページ(last_processed_page_num == 0)なら1と仮定
                                if last_processed_page_num == 0:
                                    print("        最初のページ(1)として処理を試みます...")
                                    current_active_page_num = 1
                                else:
                                    # アクティブページが特定できない場合はエラーとして中断
                                    print("        [エラー] アクティブページを特定できず、処理を続行できません。")
                                    field_processed_successfully = False; year_processed_successfully = False; break

                            # 現在のアクティブページが未処理の場合、処理を実行
                            if current_active_page_num > last_processed_page_num and current_active_page_num not in current_page_links_processed_in_block:
                                print(f"        ページ {current_active_page_num} を処理します...")
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
                                    print(f"        ページ {current_active_page_num} で {len(urls_on_page)} 件のリンクを取得。")

                                    main_window = driver.current_window_handle
                                    for index, syllabus_url in enumerate(urls_on_page):
                                        if syllabus_url in opened_links_this_year_field:
                                            # print(f"           詳細処理 {index + 1}/{len(urls_on_page)}: スキップ (処理済み) {syllabus_url}")
                                            continue # 既に処理済みのリンクはスキップ

                                        print(f"\n           詳細処理 {index + 1}/{len(urls_on_page)}: {syllabus_url}")
                                        syllabus_details = None
                                        detail_success = False
                                        try:
                                            if check_session_timeout(driver, screenshots_dir): raise InvalidSessionIdException("Session timeout before detail fetch")
                                            initial_handles = set(driver.window_handles)
                                            driver.execute_script(f"window.open('{syllabus_url}', '_blank');") # 新しいタブで開く
                                            # 新しいタブが開くまで待機
                                            WebDriverWait(driver, MEDIUM_WAIT).until(lambda d: len(d.window_handles) == len(initial_handles) + 1)
                                            new_handle = list(set(driver.window_handles) - initial_handles)[0]
                                            driver.switch_to.window(new_handle) # 新しいタブに切り替え
                                            time.sleep(SHORT_WAIT) # ★★★ タブ切り替え後の待機時間をSHORT_WAITに ★★★

                                            # ★★★ 詳細情報取得 (エラー発生時はNoneが返るか、例外が発生) ★★★
                                            syllabus_details = get_syllabus_details(driver, year, screenshots_dir)

                                            if syllabus_details:
                                                scraped_data_all_years.append(syllabus_details)
                                                opened_links_this_year_field.add(syllabus_url) # 処理済みURLに追加
                                                processed_count_on_page += 1
                                                detail_success = True
                                            else:
                                                # get_syllabus_detailsがNoneを返した場合 (予期せぬエラーなど)
                                                print(f"           [警告] URL {syllabus_url} の詳細情報取得失敗 (None返却)。")
                                                # Noneが返った場合は致命的ではないので続行

                                        except MissingCriticalDataError as e_critical_detail:
                                            # 必須データ欠落エラー (get_syllabus_details内で発生)
                                            print(f"           [エラー] {e_critical_detail}。この科目をスキップします。")
                                            # 必須データ欠落は個別の科目の問題として扱い、ループは続行
                                        except (InvalidSessionIdException, NoSuchWindowException) as e_session_detail:
                                            # 詳細取得中のセッション/ウィンドウエラーは致命的
                                            print(f"           [エラー] 詳細処理中にセッション/ウィンドウエラー: {e_session_detail}")
                                            raise # 上位に伝播させる
                                        except Exception as e_detail:
                                            # その他の詳細取得中の予期せぬエラー
                                            print(f"           [エラー] URL {syllabus_url} の詳細処理中に予期せぬエラー: {e_detail}")
                                            traceback.print_exc()
                                            save_screenshot(driver, f"detail_proc_unknown_error_{year}_{field_name}", screenshots_dir)
                                            # 予期せぬエラーは個別の科目の問題として扱い、ループは続行
                                        finally:
                                            # 必ず元のタブに戻る処理
                                            current_handle = driver.current_window_handle
                                            if current_handle != main_window:
                                                try: driver.close() # 詳細タブを閉じる
                                                except Exception: pass
                                            try:
                                                # 元のウィンドウが存在するか確認してから切り替え
                                                if main_window in driver.window_handles:
                                                    driver.switch_to.window(main_window)
                                                else:
                                                    # メインウィンドウが失われた場合は致命的エラー
                                                    raise NoSuchWindowException("Main window lost after processing detail tab.")
                                            except Exception as e_switch:
                                                print(f"           [エラー] メインウィンドウへの切り替え失敗: {e_switch}")
                                                raise # 致命的エラーとして処理
                                            time.sleep(0.5) # タブを閉じて切り替えた後の短い待機

                                    # --- 詳細処理ループ終了 (urls_on_page) ---
                                    print(f"        ページ {current_active_page_num} の {processed_count_on_page}/{len(urls_on_page)} 件の詳細を処理。")

                                except (TimeoutException, StaleElementReferenceException) as e_link:
                                    print(f"        [警告] ページ {current_active_page_num} のリンク取得/処理中にエラー: {e_link}")
                                    # リンク取得失敗はページの問題として扱い、次のページネーションへ
                                except (InvalidSessionIdException, NoSuchWindowException) as e_session_page:
                                    # ページ内の詳細処理ループ中のセッションエラーは致命的
                                    print(f"        [エラー] ページ {current_active_page_num} 処理中にセッション/ウィンドウエラー: {e_session_page}")
                                    field_processed_successfully = False; year_processed_successfully = False; break # ページネーションループを抜ける
                                except Exception as e_page_proc:
                                    print(f"        [エラー] ページ {current_active_page_num} の処理中に予期せぬエラー: {e_page_proc}")
                                    traceback.print_exc()
                                    field_processed_successfully = False; year_processed_successfully = False; break # ページネーションループを抜ける

                                # アクティブページの処理が完了したら記録
                                last_processed_page_num = current_active_page_num
                                current_page_links_processed_in_block.add(current_active_page_num)
                                pagination_processed_in_block = True

                            # --- アクティブページ処理終了 ---
                            if not field_processed_successfully: break # エラー発生時はページネーションループ中断

                            # クリック可能なページ番号リンクを取得 (アクティブと無効を除く数字リンク)
                            page_number_elements_info = []
                            page_number_links_xpath = ".//li[not(contains(@class, 'active')) and not(contains(@class, 'disabled'))]/a[number(text()) = number(text())]"
                            page_number_elements = pagination_container.find_elements(By.XPATH, page_number_links_xpath)

                            for link_element in page_number_elements:
                                try:
                                    page_num_text = normalize_text(link_element.text)
                                    page_num = int(page_num_text)
                                    # まだ処理していないページ番号のみを対象
                                    if page_num > last_processed_page_num and page_num not in current_page_links_processed_in_block:
                                        page_number_elements_info.append((page_num, link_element))
                                except (ValueError, StaleElementReferenceException):
                                    continue # 数字でないか、要素が古くなった場合は無視

                        except (NoSuchElementException, TimeoutException) as e_paginate_find:
                            # ページネーション自体が見つからない場合 (1ページしかないなど)
                            if last_processed_page_num <= 1 and current_active_page_num <= 1: # 最初のページしか処理していない or 処理できなかった
                                print("        ページネーション要素が見つからないか、最初のページのみです。")
                                if current_active_page_num > 0: # 最初のページが正常に処理された場合
                                     pagination_processed_in_block = True
                            else:
                                print(f"        [警告] ページネーション要素の取得に失敗: {e_paginate_find}。")
                            # ページネーションが見つからなくても、現在のページが処理済みならループを抜ける準備
                            if current_active_page_num > 0 and current_active_page_num == last_processed_page_num:
                                print("        これ以上処理するページはありません。")
                            break # ページネーションループを抜ける
                        except Exception as e_paginate_outer:
                             print(f"        [エラー] ページネーション処理中に予期せぬエラー: {e_paginate_outer}")
                             traceback.print_exc()
                             field_processed_successfully = False; year_processed_successfully = False; break


                        # ページ番号順にソート
                        page_number_elements_info.sort(key=lambda x: x[0])

                        # --- 2. 取得したページ番号リンクを順番にクリックして処理 ---
                        clicked_page_link = False
                        for page_num, link_element_stub in page_number_elements_info:
                            print(f"        ページ {page_num} への遷移を試みます...")
                            try:
                                # クリック直前に要素を再検索してStale対策
                                link_to_click = WebDriverWait(driver, SHORT_WAIT).until(
                                    EC.element_to_be_clickable((By.XPATH, f"//ul[contains(@class, 'pagination')]//li/a[normalize-space(text())='{page_num}']"))
                                )
                                if click_element(driver, link_to_click):
                                    print(f"        ページ {page_num} へ遷移。結果待機中...")
                                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                    time.sleep(MEDIUM_WAIT) # ★★★ ページ遷移後の待機時間をMEDIUM_WAITに ★★★
                                    clicked_page_link = True
                                    # ページ遷移に成功したら、このブロックのページ番号処理ループを抜け、
                                    # 次のページネーションループの冒頭でアクティブページとして処理される
                                    break
                                else:
                                    print(f"        [警告] ページ {page_num} のクリックに失敗。次のページ番号を試します。")
                                    continue # 次のページ番号へ

                            except (TimeoutException, StaleElementReferenceException, NoSuchElementException) as e_click:
                                print(f"        [警告] ページ {page_num} の検索/クリック中にエラー: {e_click}。次のページ番号を試します。")
                                continue # 次のページ番号へ
                            except Exception as e_proc_outer:
                                print(f"        [エラー] ページ {page_num} の処理中に予期せぬエラー: {e_proc_outer}")
                                traceback.print_exc()
                                field_processed_successfully = False; year_processed_successfully = False # 年度/分野処理失敗フラグ
                                break # このブロックのページ番号処理を中断 -> ページネーションループも抜ける

                        # --- ページ番号クリックループ終了 ---
                        if not field_processed_successfully: break # エラー発生時はページネーションループ中断
                        if clicked_page_link: continue # ページ遷移成功時は次のページネーションループへ

                        # --- 3. 「次へ」ボタンの処理 (ページ番号クリックがなかった場合) ---
                        if not clicked_page_link and page_number_elements_info: # ページ番号があったのにクリックできなかった場合
                             print("        [警告] 表示されているページ番号リンクへの遷移に全て失敗しました。")
                             # 「次へ」を試みるか、中断するか？ -> ここでは「次へ」を試みる

                        try:
                            # 「次へ」ボタンを再検索
                            pagination_container = WebDriverWait(driver, SHORT_WAIT).until(
                                EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]"))
                            )
                            next_xpath = ".//li[not(contains(@class, 'disabled'))]/a[contains(text(), '次') or contains(., 'Next')]"
                            next_button = pagination_container.find_element(By.XPATH, next_xpath)

                            print(f"\n        ページ番号 {last_processed_page_num} まで処理完了。「次へ」をクリックします...")
                            if click_element(driver, next_button):
                                print("        「次へ」をクリックしました。結果待機中...")
                                WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                time.sleep(MEDIUM_WAIT) # ★★★ ページ遷移後の待機時間をMEDIUM_WAITに ★★★
                                pagination_processed_in_block = True
                                # last_processed_page_num は次のループの開始時にアクティブページから更新される
                                continue # 次のページネーションブロックへ
                            else:
                                print("        [警告] 「次へ」ボタンのクリックに失敗。ページネーションを終了します。")
                                break # ページネーションループ終了
                        except (NoSuchElementException, TimeoutException):
                            # 「次へ」ボタンがないか無効の場合
                            print(f"\n        ページ番号 {last_processed_page_num} まで処理完了。「次へ」ボタンが見つからないか無効です。ページネーションを終了します。")
                            break # ページネーションループ終了
                        except Exception as e_next:
                            print(f"        [エラー] 「次へ」ボタンの検索/クリック中にエラー: {e_next}。ページネーションを終了します。")
                            traceback.print_exc()
                            break # ページネーションループ終了

                    # --- ページネーションループ終了 ---
                    if not field_processed_successfully:
                         print(f"--- 分野 {field_name} ({year}年度) 処理中にエラーが発生したため中断 ---")
                         # エラーが発生した場合、この分野の処理は失敗


                # --- 分野ループの try...except...finally ---
                except (InvalidSessionIdException, NoSuchWindowException) as e_session_field:
                    # 分野ループ中にセッション/ウィンドウエラーが発生した場合
                    print(f"\n[!!!] 分野 '{field_name}' ({year}年度) 処理中セッション/ウィンドウエラー: {e_session_field}。WebDriver再起動試行。")
                    if driver:
                        try: driver.quit()
                        except Exception as quit_err: print(f" WebDriver終了エラー: {quit_err}")
                    driver = None # quit試行後、driverをNoneに設定
                    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                    if not driver:
                        print("[!!!] WebDriver再初期化失敗。スクリプトを終了します。")
                        raise Exception("WebDriver再初期化失敗。") # メインのtryを抜ける
                    try:
                        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                            print("[!!!] 再ログイン失敗。スクリプトを終了します。")
                            raise Exception("再ログイン失敗。") # メインのtryを抜ける
                    except Exception as relogin_e:
                        print(f"[!!!] 再ログイン中にエラー: {relogin_e}")
                        raise # メインのtryを抜ける

                    print(f" WebDriver再起動・再ログイン完了。分野 '{field_name}' ({year}年度) 再試行。")
                    # field_index は変えずに continue するが、whileループなので field_index のインクリメントが必要
                    # -> field_index を変えずに再試行するには、whileループの最後にインクリメントしないようにする必要がある
                    # -> または、ここで field_index をデクリメントする
                    field_index -= 1 # 次のループで同じ分野を再試行するためにデクリメント
                    field_processed_successfully = False # 再試行するので、この回の処理は成功ではない
                    year_processed_successfully = False # 年度も成功ではない
                except Exception as e_field_main:
                     # その他の分野ループ中のエラー
                    print(f"     [エラー] 分野 '{field_name}' ({year}年度) 処理中エラー: {e_field_main}")
                    traceback.print_exc()
                    save_screenshot(driver, f"field_main_error_{year}_{field_name}", screenshots_dir)
                    print(" この分野をスキップします。")
                    field_processed_successfully = False # この分野は失敗
                    year_processed_successfully = False # この年度も失敗扱いとする
                finally:
                    # ★★★ 分野処理完了後にJSON書き込み ★★★
                    if field_processed_successfully:
                        print(f"===== 分野: {field_name} ({year}年度) 正常終了 =====")
                        # 成功時のみJSON書き込みを試行
                        if scraped_data_all_years:
                            print("\n--- JSONファイル更新 ---")
                            final_data = aggregate_syllabus_data(scraped_data_all_years)
                            write_json_data(final_data, output_json_path)
                        else:
                            print("収集データがないためJSONは更新されません。")
                    else:
                        print(f"===== 分野: {field_name} ({year}年度) 処理中断または失敗 =====")
                        # エラー発生時も、それまでのデータを書き込む（オプション）
                        if scraped_data_all_years:
                            print("\n--- JSONファイル更新 (エラー発生時点) ---")
                            final_data = aggregate_syllabus_data(scraped_data_all_years)
                            write_json_data(final_data, output_json_path)

                    # 次の分野へ
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
                save_screenshot(driver, "fatal_error_global", screenshots_dir)
            except Exception as ss_err:
                print(f"[警告] エラー発生後のスクリーンショット保存に失敗しました: {ss_err}")
    finally:
        # --- 終了処理 ---
        if driver:
            try:
                driver.quit()
                print("\nブラウザ終了。")
            except Exception as qe:
                print(f"\nブラウザ終了時エラー: {qe}")

        # ★★★ 最終書き込み ★★★
        print("\n=== 最終処理: JSONファイル書き込み ===")
        if scraped_data_all_years:
            print(f"合計 {len(scraped_data_all_years)} 件の生データ取得。")
            print("\n最終データ集約中...")
            final_json_data = aggregate_syllabus_data(scraped_data_all_years)
            if final_json_data:
                write_json_data(final_json_data, output_json_path)
            else:
                print("集約後データなし。JSON未作成。")
        else:
            print("\n有効データ収集されず。JSON未作成。")

        end_time = time.time()
        elapsed_time = end_time - global_start_time
        print(f"\n処理時間: {elapsed_time:.2f} 秒")
        print(f"スクレイピング終了: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")