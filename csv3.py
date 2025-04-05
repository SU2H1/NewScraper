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
# ★★★ 修正箇所: 要素待機時間を再々延長 ★★★
ELEMENT_WAIT_TIMEOUT = 60 # 要素が表示されるまでの最大待機時間(秒)
SHORT_WAIT = 3 # 短い待機時間(秒)
MEDIUM_WAIT = 5 # 中程度の待機時間(秒)
LONG_WAIT = 10 # 長い待機時間(秒)

# --- ★ カスタム例外クラス ★ ---
class MissingCriticalDataError(Exception):
    """必須データまたは定義済みデータが取得できなかった場合に発生させる例外"""
    pass

# --- ヘルパー関数 ---

def create_output_dirs(base_dir=OUTPUT_DIR_NAME):
    """
    出力用のディレクトリ（ベース、ログ、スクリーンショット）を作成する。
    """
    logs_dir = os.path.join(base_dir, "logs")
    screenshots_dir = os.path.join(base_dir, "screenshots")
    for dir_path in [base_dir, logs_dir, screenshots_dir]:
        os.makedirs(dir_path, exist_ok=True) # exist_ok=True で既に存在してもエラーにしない
    return base_dir, logs_dir, screenshots_dir

def save_screenshot(driver, prefix="screenshot", dir_path="screenshots"):
    """
    現在の画面のスクリーンショットを指定されたディレクトリに保存する。
    ファイル名にはタイムスタンプが付与される。
    WebDriverが無効な場合やセッションエラー時はNoneを返す。
    """
    # WebDriverが無効、またはセッションIDがない場合は保存しない
    if not driver or not hasattr(driver, 'session_id') or driver.session_id is None:
        print("[警告] WebDriverが無効またはセッションIDがないため、スクリーンショットを保存できません。")
        return None
    try:
        # ファイル名を生成 (プレフィックス + タイムスタンプ)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(dir_path, filename)
        # スクリーンショットを保存
        driver.save_screenshot(filepath)
        print(f"スクリーンショットを保存しました: {filepath}")
        return filepath
    except InvalidSessionIdException:
        # セッションIDが無効な場合 (ブラウザが閉じられた後など)
        print("[警告] スクリーンショット保存試行中にInvalidSessionIdExceptionが発生しました。")
        return None
    except WebDriverException as e:
        # その他のWebDriver関連エラー
        print(f"[エラー] スクリーンショットの保存に失敗: {e}")
    except Exception as e:
        # 予期せぬエラー
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
        # 要素をクリック
        element.click()
        time.sleep(0.3) # クリック後の短い待機
        return True
    except ElementClickInterceptedException:
        # 通常のクリックが他の要素によって妨げられた場合
        # print("      通常のClickが妨害されたため、JavaScriptでClickを試みます。") # Log suppressed
        try:
            # 要素が画面内に表示されるようにスクロール
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
            time.sleep(0.3) # スクロール後の待機
            # JavaScript を使用してクリックを実行
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.3) # クリック後の短い待機
            return True
        except Exception as js_e:
            # JavaScriptでのクリックも失敗した場合
            print(f"      JavaScript Click中にエラー: {js_e}")
            return False
    except StaleElementReferenceException:
        # 要素が古くなった場合 (DOMが変更されたなど)
        print("      Click試行中に要素がStaleになりました。再取得が必要です。")
        return False
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        # セッションIDが無効、またはウィンドウが存在しない場合は、例外を再発生させて上位で処理
        print(f"      Click中にセッション/ウィンドウエラー: {e_session}")
        raise
    except Exception as e:
        # その他の予期せぬエラー
        print(f"      Click中に予期せぬエラー: {e}")
        return False

def select_option_by_text(driver, select_element, option_text, fallback_to_js=True):
    """
    Select要素から表示テキストでオプションを選択する。
    通常の選択が失敗した場合、JavaScriptによる選択を試みる (fallback_to_js=Trueの場合)。
    """
    try:
        select_obj = Select(select_element)
        # 表示テキストでオプションを選択
        select_obj.select_by_visible_text(option_text)
        time.sleep(0.3) # 選択後の待機
        # 選択が正しく反映されたか確認
        selected_option = Select(select_element).first_selected_option
        if selected_option.text.strip() == option_text:
            return True
        else:
            # 選択したはずのテキストと実際の選択テキストが異なる場合
            # print(f"    [警告] select_by_visible_text後、選択値が '{selected_option.text.strip()}' となり期待値 '{option_text}' と異なります。") # Log suppressed
            raise Exception("Selection did not reflect correctly.") # 選択が反映されなかったことを示す例外
    except Exception as e:
        # 通常の select_by_visible_text が失敗した場合
        # print(f"    通常の select_by_visible_text 失敗: {e}") # Log suppressed
        if fallback_to_js:
            # JavaScriptによるフォールバックを試みる
            # print("      通常の選択が失敗したため、JavaScriptでの選択を試みます。") # Log suppressed
            try:
                # JavaScript を使用して指定されたテキストを持つオプションを探し、選択状態にする
                js_script = f"""
                    let select = arguments[0]; let optionText = arguments[1];
                    for(let i = 0; i < select.options.length; i++) {{
                        if(select.options[i].text.trim() === optionText) {{
                            select.selectedIndex = i;
                            // change イベントと input イベントを発火させて、選択の変更を他のスクリプトに通知
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true; // 選択成功
                        }}
                    }}
                    return false; // オプションが見つからない
                """
                result = driver.execute_script(js_script, select_element, option_text)
                if result:
                    time.sleep(0.5) # JS選択後の待機
                    # JSでの選択が正しく反映されたか再度確認
                    selected_option_text_js = driver.execute_script("return arguments[0].options[arguments[0].selectedIndex].text.trim();", select_element)
                    if selected_option_text_js == option_text:
                        return True
                    else:
                        # print(f"    [警告] JavaScriptでの選択後も値が期待通りではありません (現在値: '{selected_option_text_js}')。") # Log suppressed
                        return False
                else:
                    # JavaScriptでもオプションが見つからなかった場合
                    # print(f"    JavaScriptによる選択も失敗: '{option_text}' が見つかりません。") # Log suppressed
                    return False
            except (InvalidSessionIdException, NoSuchWindowException) as e_session:
                # セッションIDが無効、またはウィンドウが存在しない場合は、例外を再発生
                print(f"      JS選択中にセッション/ウィンドウエラー: {e_session}")
                raise
            except Exception as js_error:
                # JavaScript実行中にエラーが発生した場合
                print(f"    JavaScriptによる選択中にエラー: {js_error}")
                return False
        else:
            # フォールバックが無効な場合は失敗
            return False

# --- ★★★ get_syllabus_details 関数の修正 ★★★ ---
def get_syllabus_details(driver, current_year, screenshots_dir):
    """
    シラバス詳細ページから情報を取得。
    必須情報（コースID）またはinfo_map内のいずれかの情報が欠落していたら MissingCriticalDataError を発生させる。
    """
    details = {'year_scraped': current_year} # スクレイピングした年度を記録
    current_url = "N/A"
    try:
        current_url = driver.current_url # 現在のURLを取得
        # --- ページの主要要素が表示されるまで待機 ---
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")) # Wait for body tag first
        )
        # bodyタグが見つかった後、JavaScriptによる描画などを考慮して追加で待機
        time.sleep(5) # 5秒待機 (必要に応じて調整)

    except TimeoutException:
        # ページ読み込みがタイムアウトした場合
        print(f"  [エラー] 詳細ページの基本要素(body)読み込みタイムアウト。 URL: {current_url}")
        save_screenshot(driver, f"detail_load_timeout_{current_year}", screenshots_dir)
        return None # タイムアウトは続行不能としてNoneを返す
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
        # セッション/ウィンドウエラーは上位で処理するため再発生
        print(f"  [エラー] 詳細ページ読み込み中にセッション/ウィンドウエラー: {e_session}")
        raise # ★ このエラーは上位で処理
    except WebDriverException as e:
        # その他のWebDriverエラー (ネットワークエラーなど)
        print(f"  [エラー] 詳細ページ読み込み中にWebDriverエラー: {e} URL: {current_url}")
        save_screenshot(driver, f"detail_load_error_{current_year}", screenshots_dir)
        return None
    except Exception as e:
        # 予期せぬエラー
        print(f"  [エラー] 詳細ページ読み込み中に予期せぬエラー: {e} URL: {current_url}")
        save_screenshot(driver, f"detail_load_unknown_error_{current_year}", screenshots_dir)
        return None

    # --- Course ID 取得 ---
    details['course_id'] = None # 初期化
    try:
        # URLのクエリパラメータやパスからIDを正規表現で抽出 (複数のパターンに対応)
        id_match = re.search(r'[?&]id=(\d+)', current_url) or \
                   re.search(r'/syllabus/(\d+)', current_url) or \
                   re.search(r'[?&]entno=(\d+)', current_url)
        if id_match:
            details['course_id'] = id_match.group(1)
        else:
            # URLから取得できない場合、テーブル内の登録番号 or 隠しinput要素から取得試行
            try:
                # 登録番号(entno) がテーブル内にあるか試す (XPathはHTMLに依存)
                reg_num_th = driver.find_element(By.XPATH, "//tr/th[normalize-space()='登録番号']")
                reg_num_td = reg_num_th.find_element(By.XPATH, "./following-sibling::td")
                reg_num = normalize_text(reg_num_td.text)
                if reg_num and reg_num.isdigit():
                    details['course_id'] = reg_num
                else:
                    # テーブル内にもなければ隠し要素を探す
                    hidden = driver.find_element(By.XPATH, "//input[@type='hidden' and (contains(@name, 'id') or contains(@name, 'entno'))]")
                    value = hidden.get_attribute('value')
                    if value and value.isdigit(): # 値が存在し、数字であるか確認
                        details['course_id'] = value
            except NoSuchElementException:
                # 登録番号や隠し要素が見つからなくてもここではエラーにしない（次のチェックで判断）
                pass
    except Exception as e:
        print(f"  [警告] Course ID の取得中にエラー: {e}")

    # ★★★ Course IDが取得できなかった場合に例外を発生させる ★★★
    if not details.get('course_id'):
        error_message = f"必須データ(Course ID)の取得に失敗しました (URL: {current_url})"
        print(f"  [エラー] {error_message}")
        raise MissingCriticalDataError(error_message) # ★ スクリプト停止のために例外を発生

    # --- 各情報の取得 ---
    # ★★★ XPathは実際のHTMLに合わせて【必ず】修正してください ★★★
    # 取得したい情報とそのXPath、取得できなかった場合のデフォルト値、検索方法(デフォルトはXPATH)をマッピング
    info_map = {
        # --- 必須項目 (これらが取得できない、または不適切な場合はエラーとする) ---
        'name_ja': ("科目名", "//h2[@class='class-name']", f"名称不明-{details.get('course_id', 'ID不明')}", By.XPATH),
        'semester_ja': ("学期", "//tr[th[normalize-space()='年度・学期']]/td", "学期不明"),
        # --- オプショナル項目 (ただし、取得失敗時はエラーとする方針に変更) ---
        'professor_ja': ("担当者名", "//tr[th[contains(text(),'担当者名')]]/td", ""), # デフォルトは空文字
        'credits_ja': ("単位", "//tr[th[contains(text(),'単位')]]/td", "単位不明"),
        'field_ja': ("分野", "//tr[th[contains(text(),'分野')]]/td", "分野不明"),
        'location_ja': ("教室", "//tr[th[contains(text(),'教室')]]/td", "教室不明"),
        'day_period_ja': ("曜日時限", "//tr[th[contains(text(),'曜日時限')]]/td", "曜日時限不明"),
    }

    # ★ 不適切と判断する科目名のパターン（ページのタイトルなど、誤って取得する可能性のある文字列）
    INVALID_COURSE_NAME_PATTERNS = ["慶應義塾大学 シラバス・時間割"]

    # --- 必須情報フラグ (info_map内のいずれかの取得失敗でTrueになる) ---
    critical_data_missing = False # 必須情報が欠落しているかどうかのフラグ
    missing_details = [] # 欠落情報の詳細を記録するリスト

    # info_map をループして各情報を取得
    for key, (label, xpath, default_value, *find_by) in info_map.items():
        by_method = find_by[0] if find_by else By.XPATH # 検索方法指定がなければXPATHを使用
        try:
            # 要素が見つかるまで待機
            element = WebDriverWait(driver, SHORT_WAIT).until(
                EC.presence_of_element_located((by_method, xpath))
            )
            # 要素のテキストを正規化して取得
            text_content = normalize_text(element.text)
            # テキストが空でなければ採用、空ならデフォルト値を使用
            details[key] = text_content if text_content else default_value

            # --- ★ 科目名のみ特別な内容チェック ★ ---
            if key == 'name_ja':
                # デフォルト値と同じ、または不適切パターンに含まれる場合はエラーと判断
                if details[key] == default_value or any(pattern in details[key] for pattern in INVALID_COURSE_NAME_PATTERNS):
                    critical_data_missing = True
                    missing_details.append(f"{label}: 取得値「{details[key]}」が不適切 (XPath: {xpath})")
                    details[key] = default_value # 値をデフォルトに戻しておく

        except TimeoutException: # WebDriverWaitでタイムアウトした場合
            details[key] = default_value
            # ★★★ 修正: どのキーでもタイムアウトしたらエラーと判断 ★★★
            critical_data_missing = True
            missing_details.append(f"{label}: 要素取得タイムアウト (XPath: {xpath})")
            print(f"  [エラー] {label} ({xpath}) の取得中にタイムアウトしました。") # エラーログ追加

        except NoSuchElementException:
            # 要素が見つからない場合
            details[key] = default_value
            # ★★★ 修正: どのキーでも要素が見つからなければエラーと判断 ★★★
            critical_data_missing = True
            missing_details.append(f"{label}: 要素が見つかりません (XPath: {xpath})")
            print(f"  [エラー] {label} ({xpath}) が見つかりませんでした。") # エラーログ追加

        except StaleElementReferenceException:
            # 要素が古くなった場合（DOMが変更されたなど）
            details[key] = default_value
            print(f"  [警告] {label} ({xpath}) の取得中に要素がStaleになりました。デフォルト値「{default_value}」を使用。処理は続行します。")
            # Staleの場合は今回はエラーにしない（再試行で取得できる可能性があるため）

        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
            # セッション/ウィンドウエラーは上位で処理するため再発生
            print(f"  [エラー] {label} 取得中にセッション/ウィンドウエラー: {e_session}")
            raise # ★ 上位で処理
        except Exception as e:
            # その他の予期せぬエラー
            details[key] = default_value
            print(f"  [警告] {label} ({xpath}) の取得中に予期せぬエラー: {e}。デフォルト値「{default_value}」を使用。処理は続行します。")
            # 不明なエラーの場合も今回はエラーにしない

    # --- ★ 必須データまたは定義済みデータ欠落があれば例外発生 ---
    # (info_map 内のいずれかの要素取得で Timeout/NoSuchElement が発生した場合、または科目名が不適切だった場合)
    if critical_data_missing:
        error_message = f"必須または定義済みデータの取得に失敗しました (URL: {current_url}): {'; '.join(missing_details)}"
        print(f"  [エラー] {error_message}")
        # カスタム例外を発生させてスクリプトを停止させる
        raise MissingCriticalDataError(error_message) # ★ スクリプト停止のために例外を発生

    # --- 英語情報の仮設定 (日本語情報をコピー) ---
    # まず日本語の情報を英語のキーにも入れておく
    details['professor_en'] = details.get('professor_ja', '')
    details['name_en'] = details.get('name_ja', '')
    details['credits_en'] = details.get('credits_ja', '')
    details['field_en'] = details.get('field_ja', '')
    details['location_en'] = details.get('location_ja', '')
    details['semester_en'] = details.get('semester_ja', '')
    details['day_period_en'] = details.get('day_period_ja', '')

    # --- 可能であれば英語情報を取得/変換 ---
    # (学期情報の英語変換)
    try:
        sem_elem = driver.find_element(By.XPATH, "//tr[th[normalize-space()='年度・学期']]/td")
        en_sem = sem_elem.get_attribute('data-en-value')
        if en_sem:
            details['semester_en'] = normalize_text(en_sem)
        else:
            sem_map = {"春学期": "Spring", "秋学期": "Fall", "通年": "Full Year"}
            ja_sem_text = normalize_text(sem_elem.text)
            matched_key = None
            for key in sem_map:
                if key in ja_sem_text:
                    matched_key = key
                    break
            if matched_key:
                 details['semester_en'] = sem_map[matched_key]
    except Exception as e_sem_en:
        pass # 英語情報取得に失敗しても処理は続行

    # (曜日時限情報の英語変換)
    try:
        dp_elem = driver.find_element(By.XPATH, "//tr[th[contains(text(),'曜日時限')]]/td")
        en_dp = dp_elem.get_attribute('data-en-value')
        if en_dp:
            details['day_period_en'] = normalize_text(en_dp)
        else:
            ja_dp = details.get('day_period_ja', '')
            day_map = {"月": "Mon", "火": "Tue", "水": "Wed", "木": "Thu", "金": "Fri", "土": "Sat", "日": "Sun"}
            parts = ja_dp.split()
            if len(parts) >= 1 and parts[0] in day_map:
                 details['day_period_en'] = f"{day_map[parts[0]]} {' '.join(parts[1:])}".strip()
            elif ja_dp:
                 details['day_period_en'] = ja_dp
    except Exception as e_dp_en:
        pass # 英語情報取得に失敗しても処理は続行

    return details

# --- aggregate_syllabus_data 関数 (変更なし) ---
def aggregate_syllabus_data(all_raw_data):
    """
    複数年度にわたる生データを集約し、最終的なJSON形式に整形する。
    course_id, professor_ja(担当者), semester_en(英語学期) をキーとしてデータをグループ化し、
    最新年度の情報を基に、yearフィールドに収集した全年度を記録する。
    """
    if not all_raw_data:
        return [] # データがなければ空リストを返す

    grouped_by_key = {} # 集約キーごとのデータリストを格納する辞書
    skipped_count = 0 # Course ID がなくてスキップされた件数

    # データをキーでグループ化
    for item in all_raw_data:
        course_id = item.get('course_id')
        # Course ID がないデータは集約できないためスキップ
        if not course_id:
            skipped_count += 1
            continue

        # 担当者名を "/" で分割し、空白削除、ソートしてタプルに変換（順序を固定するため）
        professors_str = item.get('professor_ja', '')
        professors = tuple(sorted([p.strip() for p in professors_str.split('/') if p.strip()]))

        # 集約キーに使用する学期情報 (英語優先、なければ日本語、それもなければ 'unknown')
        semester_en = item.get('semester_en', item.get('semester_ja', 'unknown'))
        # "学期不明" や "曜日時限不明" などの無効な値も 'unknown' に統一
        if not semester_en or semester_en in ["学期不明", "曜日時限不明"]:
            semester_en = "unknown"

        # 集約キー (コースID, 担当者名タプル, 英語学期)
        agg_key = (course_id, professors, semester_en)

        # キーが存在しなければ新しいリストを作成して追加
        if agg_key not in grouped_by_key:
            grouped_by_key[agg_key] = []
        grouped_by_key[agg_key].append(item) # 同じキーのリストにデータを追加

    if skipped_count > 0:
        print(f"ID不足により {skipped_count} 件のデータが集約からスキップされました。")

    final_list = [] # 最終的な集約済みデータリスト
    # グループ化されたデータを処理
    for agg_key, year_data_list in grouped_by_key.items():
        # 同じキーのデータを収集年度 (year_scraped) で降順ソート（最新年度のデータが先頭に来るように）
        year_data_list.sort(key=lambda x: x['year_scraped'], reverse=True)
        # 最新年度のデータを取得 (ソートしたのでリストの最初の要素)
        latest_data = year_data_list[0]
        # このキーで収集した全ての年度をリストアップし、重複排除してソート
        years_scraped = sorted(list(set(d['year_scraped'] for d in year_data_list)))

        # 最新データから各情報を取得（存在しない場合のデフォルト値も設定）
        day_period_ja = latest_data.get('day_period_ja', '曜日時限不明')
        day_period_en = latest_data.get('day_period_en', 'unknown') # 集約キーと同じものを使う
        location_ja = latest_data.get('location_ja', '教室不明')
        location_en = latest_data.get('location_en', 'unknown') # 英語情報は日本語情報をデフォルトに

        # 最終的なJSONオブジェクトの構造を定義
        aggregated_item = {
            "course_id": latest_data['course_id'], # コースID
            "year": "、".join(map(str, years_scraped)), # 収集年度を全角カンマ区切り文字列に
            "semester": semester_en, # 集約キーに使用した英語学期
            "day_period": day_period_en, # 最新データの英語曜日時限
            "professor_ja": latest_data.get('professor_ja', ''), # 最新データの担当者名(日本語)
            "translations": { # 日本語と英語の情報をネスト
                "ja": {
                    "name": latest_data.get('name_ja', ''),
                    "field": latest_data.get('field_ja', ''),
                    "credits": latest_data.get('credits_ja', ''),
                    "semester": latest_data.get('semester_ja', ''), # 最新データの日本語学期
                    "day_period": day_period_ja, # 最新データの日本語曜日時限
                    "location": location_ja, # 最新データの日本語教室
                },
                "en": {
                    "name": latest_data.get('name_en', ''), # 最新データの英語科目名
                    "field": latest_data.get('field_en', ''), # 最新データの英語分野
                    "credits": latest_data.get('credits_en', ''), # 最新データの英語単位
                    "semester": semester_en, # 集約キーに使用した英語学期
                    "day_period": day_period_en, # 最新データの英語曜日時限
                    "location": location_en, # 最新データの英語教室
                }
            }
        }
        final_list.append(aggregated_item) # 集約済みリストに追加

    return final_list

# --- login 関数 ---
def login(driver, email, password, screenshots_dir):
    """指定された情報でログイン処理を行う"""
    login_url = 'https://gslbs.keio.jp/syllabus/search' # ログイン/検索ページのURL
    max_login_attempts = 2 # 最大ログイン試行回数
    for attempt in range(max_login_attempts):
        print(f"\nログイン試行 {attempt + 1}/{max_login_attempts}...")
        try:
            # print(f"ログインページにアクセス: {login_url}") # Log suppressed
            driver.get(login_url)
            # メールアドレス入力フィールドが表示されるまで待機
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @name='identifier']")))
            time.sleep(SHORT_WAIT) # 描画安定のための待機

            # メールアドレス入力
            username_field = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='email' or @name='identifier']")))
            username_field.clear() # 既存の入力をクリア
            username_field.send_keys(email) # メールアドレスを入力
            time.sleep(0.5) # 入力後の短い待機

            # 「次へ」ボタンをクリック (複数のセレクタ候補を試す)
            next_button_selectors = ["//button[contains(., 'Next')]", "//button[contains(., '次へ')]", "//button[@type='submit']", "//input[@type='submit' and (contains(@value, 'Next') or contains(@value, '次へ'))]", "//div[@role='button' and (contains(., 'Next') or contains(., '次へ'))]" ]
            next_button = None
            for selector in next_button_selectors:
                try:
                    next_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if click_element(driver, next_button):
                        break # クリック成功したらループを抜ける
                    else:
                        next_button = None # click_elementがFalseを返した場合
                except TimeoutException:
                    continue # 次のセレクタへ
                except StaleElementReferenceException:
                    time.sleep(1); continue # 要素が古くなった場合は少し待ってリトライ
                except (InvalidSessionIdException, NoSuchWindowException) as e_session:
                    raise e_session # セッション/ウィンドウエラーは上位へ

            # ボタンが見つからない/クリックできなかった場合、Enterキー送信を試す
            if not next_button:
                # print("「次へ」ボタンが見つからないかクリックできませんでした。Enterキーを送信します...") # Log suppressed
                try:
                    username_field.send_keys(Keys.RETURN) # Enterキーを送信
                except Exception as e_enter:
                    print(f"  Enterキー送信中にエラー: {e_enter}")
                    save_screenshot(driver, f"login_next_button_error_{attempt+1}", screenshots_dir)
                    raise Exception("「次へ」ボタン処理失敗")

            # パスワード入力フィールドが表示されるまで待機
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            time.sleep(SHORT_WAIT) # 描画安定のための待機

            # パスワード入力
            password_field = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            password_field.clear() # 既存の入力をクリア
            password_field.send_keys(password) # パスワードを入力
            time.sleep(0.5) # 入力後の短い待機

            # 「サインイン」ボタンをクリック (複数のセレクタ候補を試す)
            signin_button_selectors = ["//button[contains(., 'Sign in')]", "//button[contains(., 'サインイン')]", "//button[contains(., 'Verify')]", "//button[@type='submit']", "//input[@type='submit' and (contains(@value, 'Sign in') or contains(@value, 'サインイン') or contains(@value, 'Verify'))]", "//div[@role='button' and (contains(., 'Sign in') or contains(., 'サインイン') or contains(., 'Verify'))]" ]
            signin_button = None
            for selector in signin_button_selectors:
                try:
                    signin_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if click_element(driver, signin_button):
                        break # クリック成功したらループを抜ける
                    else:
                        signin_button = None # click_elementがFalseを返した場合
                except TimeoutException:
                    continue # 次のセレクタへ
                except StaleElementReferenceException:
                    time.sleep(1); continue # 要素が古くなった場合は少し待ってリトライ
                except (InvalidSessionIdException, NoSuchWindowException) as e_session:
                    raise e_session # セッション/ウィンドウエラーは上位へ

            # ボタンが見つからない/クリックできなかった場合、Enterキー送信を試す
            if not signin_button:
                # print("「サインイン」ボタンが見つからないかクリックできませんでした。Enterキーを送信します...") # Log suppressed
                try:
                    password_field.send_keys(Keys.RETURN) # Enterキーを送信
                except Exception as e_enter:
                    print(f"  Enterキー送信中にエラー: {e_enter}")
                    save_screenshot(driver, f"login_signin_button_error_{attempt+1}", screenshots_dir)
                    raise Exception("「サインイン」ボタン処理失敗")

            # ログイン成功後のページ遷移を待機 (検索ページURL or 検索ボタンの存在)
            # print("ログイン完了と検索ページへの遷移を待ちます...") # Log suppressed
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT + LONG_WAIT).until(
                EC.any_of( # いずれかの条件を満たすまで待機
                    EC.url_contains("gslbs.keio.jp/syllabus/search"), # URLに検索ページの一部が含まれる
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '検索')]")) # 検索ページのボタンなど特定の要素が存在する
                )
            )

            # ログイン成功確認
            current_url = driver.current_url
            if "gslbs.keio.jp/syllabus/search" in current_url:
                print("ログイン成功、検索ページに到達しました。")
                try:
                    # 検索ボタンがクリック可能か軽く確認 (ページの読み込み完了度の目安)
                    search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(),'検索')]"
                    WebDriverWait(driver, MEDIUM_WAIT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                except TimeoutException:
                    print("[警告] 検索画面の主要要素確認タイムアウト。")
                return True # ログイン成功
            else:
                # 期待したURLでない場合
                print(f"[警告] ログイン後のURLが期待した検索ページではありません。 URL: {current_url}")
                save_screenshot(driver, f"login_unexpected_page_{attempt+1}", screenshots_dir)
                # 2段階認証などの可能性をチェック
                if "auth" in current_url or "verify" in current_url or "duo" in current_url:
                    print("[情報] 2段階認証ページに遷移した可能性があります。")
                    raise Exception("2段階認証検出") # 2段階認証はエラーとして処理中断
                # その他の予期せぬページの場合もリトライ対象とする (ループで再試行される)

        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
            # 回復不能なエラーはリトライせずに上位に投げる
            print(f"[エラー] ログイン処理中にセッション/ウィンドウエラー (試行 {attempt + 1}): {e_session}")
            raise

        except TimeoutException as e:
            # タイムアウトした場合
            print(f"[エラー] ログイン処理中にタイムアウト (試行 {attempt + 1})。")
            save_screenshot(driver, f"login_timeout_{attempt+1}", screenshots_dir)
            if attempt == max_login_attempts - 1:
                raise e # 最終試行なら例外を再発生させて処理中断
            print("リトライします...")
            time.sleep(MEDIUM_WAIT) # リトライ前に待機

        except WebDriverException as e:
            # WebDriver関連のエラー (ネットワークエラーなど)
            print(f"[エラー] ログイン処理中にWebDriverエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_webdriver_error_{attempt+1}", screenshots_dir)
            if "net::ERR" in str(e): # エラーメッセージにネットワーク関連の文字列が含まれるか
                print("  ネットワーク接続またはURLの問題の可能性があります。")
            if attempt == max_login_attempts - 1:
                raise e # 最終試行なら例外を再発生させて処理中断
            print("リトライします...")
            time.sleep(MEDIUM_WAIT) # リトライ前に待機

        except Exception as e:
            # その他の予期せぬエラー
            print(f"[エラー] ログイン処理中に予期せぬエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_unknown_error_{attempt+1}", screenshots_dir)
            traceback.print_exc() # 詳細なトレースバックを出力
            if attempt == max_login_attempts - 1:
                raise e # 最終試行なら例外を再発生させて処理中断
            print("リトライします...")
            time.sleep(MEDIUM_WAIT) # リトライ前に待機

    # 最大試行回数を超えても成功しなかった場合
    print("ログインに失敗しました。")
    return False

# --- check_session_timeout 関数 ---
def check_session_timeout(driver, screenshots_dir):
    """
    現在のページがセッションタイムアウトページかどうかを判定する。
    URL、タイトル、ページソース内のキーワードで判断。
    """
    try:
        current_url = driver.current_url
        page_title = driver.title
        page_source = driver.page_source.lower() # 比較のために小文字に変換

        # タイムアウトを示す可能性のあるキーワードリスト
        timeout_keywords = ["セッションタイムアウト", "session timeout", "ログインし直してください", "log back in"]
        # タイムアウト時に遷移する可能性のあるURLの一部
        error_page_url_part = "/syllabus/appMsg"

        is_session_timeout = False
        # URLにエラーページ特有の部分が含まれるか
        if error_page_url_part in current_url:
            is_session_timeout = True
        # ページソースにタイムアウト関連のキーワードが含まれるか
        elif any(keyword in page_source for keyword in timeout_keywords):
            is_session_timeout = True
        # タイトルに "error" が含まれ、かつキーワードも含まれるか (より確実な判定のため)
        elif "error" in page_title.lower() and any(keyword in page_source for keyword in timeout_keywords):
            is_session_timeout = True

        # タイムアウトと判断された場合
        if is_session_timeout:
            print("[警告] セッションタイムアウトページが検出されました。")
            save_screenshot(driver, "session_timeout_detected", screenshots_dir)
            return True # タイムアウトと判定
        else:
            return False # タイムアウトではない
    except (TimeoutException, StaleElementReferenceException):
        # ページの読み込み中や要素が古い場合はタイムアウトではないと判断
        return False
    except WebDriverException as e:
        # セッションID無効やウィンドウ消失は回復不能エラーとして上位に投げる
        if "invalid session id" in str(e).lower() or "no such window" in str(e).lower():
            raise
        else:
            # その他のWebDriverエラーはログ出力してFalseを返す
            print(f"[エラー] セッションタイムアウトチェック中に予期せぬWebDriverエラー: {e}")
            save_screenshot(driver, "session_check_webdriver_error", screenshots_dir)
            return False
    except Exception as e:
        # その他の予期せぬエラー
        print(f"[エラー] セッションタイムアウトチェック中に予期せぬエラー: {e}")
        save_screenshot(driver, "session_check_unknown_error", screenshots_dir)
        traceback.print_exc()
        return False

# --- initialize_driver 関数 ---
def initialize_driver(driver_path, headless=False):
    """WebDriver (Chrome) を初期化して返す"""
    print("\nWebDriverを初期化しています...")
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'normal' # ページの読み込み完了を待つ ('eager' や 'none' も選択肢)

    # ヘッドレスモード設定
    if headless:
        options.add_argument('--headless') # ヘッドレスモードを有効化
        options.add_argument('--disable-gpu') # ヘッドレスモードで推奨されるオプション
        options.add_argument('--window-size=1920,1080') # ウィンドウサイズを指定 (一部サイトで必要)
        print("ヘッドレスモードで実行します。")

    # WebDriverの検出を避けるためのオプションなど (効果はサイトによる)
    options.add_argument('--disable-extensions') # 拡張機能を無効化
    options.add_argument('--no-sandbox') # Sandboxプロセスを無効化 (Linux環境で必要になることが多い)
    options.add_argument('--disable-dev-shm-usage') # /dev/shm パーティションの使用を無効化 (メモリ不足エラー対策)
    options.add_argument('--disable-infobars') # 「Chromeは自動テストソフトウェアによって制御されています」の通知バーを非表示
    options.add_argument('--disable-blink-features=AutomationControlled') # navigator.webdriver フラグを隠す試み
    options.add_experimental_option('excludeSwitches', ['enable-automation']) # 自動化関連のスイッチを除外
    options.add_experimental_option('useAutomationExtension', False) # 自動化拡張機能の使用を無効化

    new_driver = None
    try:
        # ChromeDriverのパスが指定されていればそれを使用、なければ自動検出
        if driver_path and os.path.exists(driver_path):
            # 指定されたパスでServiceオブジェクトを作成
            service = Service(executable_path=driver_path)
            new_driver = webdriver.Chrome(service=service, options=options)
            # print(f"指定されたChromeDriverを使用: {driver_path}") # Log suppressed
        else:
            # パスが指定されていない、または無効な場合
            print("ChromeDriverパス未指定/無効のため、システムPATHから自動検出します。")
            # Selenium 4以降では、パスがなくてもSelenium Managerが自動で適切なChromeDriverをダウンロード・管理してくれる
            new_driver = webdriver.Chrome(options=options)

        # タイムアウト設定
        new_driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT) # ページ全体の読み込みタイムアウト
        new_driver.implicitly_wait(5) # 要素が見つからない場合に待機する暗黙的な時間 (秒)

        print("WebDriverの初期化完了。")
        return new_driver

    except WebDriverException as e:
        # WebDriverの初期化自体に関するエラー
        print(f"[重大エラー] WebDriverの初期化失敗: {e}")
        error_message = str(e).lower()
        # 一般的なエラー原因に対するヒントを表示
        if "session not created" in error_message:
            print("  考えられる原因: ChromeDriver と Chrome ブラウザのバージョンが不一致です。")
            print("  対策: Chromeブラウザのバージョンを確認し、対応するChromeDriverをダウンロード・指定してください。")
        elif "executable needs to be in path" in error_message:
            print("  考えられる原因: ChromeDriver の実行ファイルがシステムPATH上にないか、CHROME_DRIVER_PATHの指定が誤っています。")
            print("  対策: ChromeDriverをダウンロードし、PATHを通すか、CHROME_DRIVER_PATH変数で正しいパスを指定してください。")
        else:
            # その他のWebDriverエラーの詳細を出力
            traceback.print_exc()
        return None # 初期化失敗時はNoneを返す

    except Exception as e:
        # その他の予期せぬエラー
        print(f"[重大エラー] WebDriver初期化中に予期せぬエラー: {e}")
        traceback.print_exc()
        return None # 初期化失敗時はNoneを返す

# --- ★★★ メイン処理 ★★★ ---
if __name__ == "__main__":
    # 出力ディレクトリ作成
    output_dir, logs_dir, screenshots_dir = create_output_dirs(OUTPUT_DIR_NAME)
    start_time_dt = datetime.datetime.now() # 開始時刻を記録
    output_json_path = os.path.join(output_dir, OUTPUT_JSON_FILE) # 出力JSONファイルのフルパス
    driver = None # driver変数を初期化
    scraped_data_all_years = [] # 全ての年度・分野の生データを格納するリスト
    global_start_time = time.time() # 処理時間計測用の開始時間
    print(f"スクレイピング開始: {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- WebDriverとログインの初期化 ---
    # WebDriverを初期化
    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
    # 初期化に失敗した場合はスクリプト終了
    if not driver:
        sys.exit("致命的エラー: WebDriverを初期化できませんでした。スクリプトを終了します。") # ★ エラーなら即終了

    try:
        # 最初のログイン試行
        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
            # ログインに失敗した場合はスクリプト終了
            sys.exit("致命的エラー: 初期ログインに失敗しました。スクリプトを終了します。") # ★ エラーなら即終了
    except Exception as initial_login_e:
         # ログイン関数内で捕捉されなかった予期せぬ例外が発生した場合
         print(f"致命的エラー: 初期ログイン中に予期せぬ例外が発生: {initial_login_e}")
         traceback.print_exc()
         # WebDriverが起動していれば終了処理を試みる
         if driver:
             try:
                 # エラー発生時のスクリーンショットを試みる
                 save_screenshot(driver, "initial_login_fatal_error", screenshots_dir)
                 driver.quit() # ブラウザを閉じる
             except Exception as qe:
                 print(f"初期ログインエラー後のブラウザ終了時エラー: {qe}")
         sys.exit(1) # エラー終了コード1で終了


    # --- メインループ (分野 -> 年度 -> ページ -> 詳細) ---
    try:
        field_index = 0
        # TARGET_FIELDS のリストをループ (分野ごと)
        while field_index < len(TARGET_FIELDS):
            field_name = TARGET_FIELDS[field_index] # 現在処理中の分野名
            print(f"\n===== 分野: {field_name} (インデックス: {field_index}) の処理開始 =====")
            # field_processed_successfully = True # 分野処理成功フラグ (エラー発生時にFalseにする) - 今回は未使用

            try:
                # --- ループ開始時にセッションタイムアウトチェック＆必要なら再ログイン ---
                # 各分野の処理開始前にセッションが有効か確認
                if check_session_timeout(driver, screenshots_dir):
                    print("セッションタイムアウト検出。再ログイン試行...")
                    if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                        # 再ログイン失敗時はこの分野をスキップ
                        print("[エラー] 再ログイン失敗。この分野をスキップします。")
                        field_index += 1 # 次の分野へ
                        continue # while field_index ループの次のイテレーションへ

                # --- 分野選択 ---
                # print(f"  分野 '{field_name}' を選択します...") # Log suppressed
                # 現在のURLが検索ページでない場合は移動 (WebDriver再起動後など)
                if "gslbs.keio.jp/syllabus/search" not in driver.current_url:
                    # print("  検索ページにいないため、移動します...") # Log suppressed
                    driver.get('https://gslbs.keio.jp/syllabus/search')
                    # URLが変わるまで待機
                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search"))
                    time.sleep(MEDIUM_WAIT) # ページ遷移後の待機

                # 分野選択ドロップダウン要素を取得
                field_select_xpath = "//select[@name='KEYWORD_FLD1CD']" # XPathは要確認
                field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                # ドロップダウンから分野名で選択
                if not select_option_by_text(driver, field_select_element, field_name):
                    # 選択に失敗した場合は警告を表示し、この分野をスキップ
                    print(f"    [警告] 分野 '{field_name}' の選択に失敗しました。この分野をスキップします。")
                    save_screenshot(driver, f"field_selection_failed_{field_name}", screenshots_dir)
                    field_index += 1 # 次の分野へ
                    continue # while field_index ループの次のイテレーションへ
                time.sleep(SHORT_WAIT) # 選択後の待機 (選択結果が反映されるのを待つ)

                # --- 年度ループ ---
                year_index = 0
                # TARGET_YEARS のリストをループ (年度ごと)
                while year_index < len(TARGET_YEARS):
                    year = TARGET_YEARS[year_index] # 現在処理中の年度
                    print(f"\n--- {year}年度 (インデックス: {year_index}) の処理開始 (分野: {field_name}) ---")
                    year_processed_successfully = True # 年度処理成功フラグ (エラー発生時にFalseにする)
                    opened_links_this_year_field = set() # この年度・分野で既に開いた詳細ページのURLを記録するセット

                    try:
                        # --- 年度ループ開始時にセッションタイムアウトチェック＆再ログイン（＋分野再選択）---
                        # 各年度の処理開始前にセッションが有効か確認
                        if check_session_timeout(driver, screenshots_dir):
                            print("セッションタイムアウト検出。再ログイン試行...")
                            if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                                # 再ログイン失敗時はこの年度をスキップ
                                print("[エラー] 再ログイン失敗。この年度をスキップします。")
                                year_index += 1 # 次の年度へ
                                continue # while year_index ループの次のイテレーションへ
                            # 再ログイン成功後、現在の分野を再選択する必要がある
                            print(f"  再ログイン成功。分野 '{field_name}' を再選択します...")
                            time.sleep(SHORT_WAIT)
                            # 検索ページに戻っているはずなので分野を選択し直す
                            if "gslbs.keio.jp/syllabus/search" not in driver.current_url:
                                driver.get('https://gslbs.keio.jp/syllabus/search')
                                WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search"))
                                time.sleep(MEDIUM_WAIT)
                            # 分野選択要素を再取得して選択
                            field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                            if not select_option_by_text(driver, field_select_element, field_name):
                                print(f"    [警告] 再ログイン後の分野 '{field_name}' 再選択に失敗しました。この年度をスキップします。")
                                year_index += 1 # 次の年度へ
                                continue # while year_index ループの次のイテレーションへ
                            time.sleep(SHORT_WAIT)

                        # --- 年度選択と検索実行 ---
                        # 検索ページにいるか確認し、必要なら移動して分野を再選択 (年度ループ内でページ遷移が発生した場合に備える)
                        if "gslbs.keio.jp/syllabus/search" not in driver.current_url:
                            # print("  検索ページにいないため、移動し、分野を再選択します...") # Log suppressed
                            driver.get('https://gslbs.keio.jp/syllabus/search')
                            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search"))
                            time.sleep(MEDIUM_WAIT)
                            # 分野選択要素を再取得して選択
                            field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                            if not select_option_by_text(driver, field_select_element, field_name):
                                print(f"    [警告] ページ移動後の分野 '{field_name}' 再選択に失敗しました。この年度をスキップします。")
                                year_index += 1; continue
                            time.sleep(SHORT_WAIT)

                        # 年度選択ドロップダウン要素を取得して選択
                        year_select_xpath = "//select[@name='KEYWORD_TTBLYR']" # XPathは要確認
                        year_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, year_select_xpath)))
                        if not select_option_by_text(driver, year_select_element, str(year)):
                            # 年度選択に失敗した場合は警告を表示し、この年度をスキップ
                            print(f"    [警告] 年度 '{year}' の選択に失敗しました。この年度をスキップします。")
                            save_screenshot(driver, f"year_selection_failed_{year}", screenshots_dir)
                            year_index += 1; continue
                        time.sleep(SHORT_WAIT) # 選択後の待機

                        # 学年「3年」のチェックボックスがあれば、チェックを外す (サイトの仕様に合わせて調整)
                        try:
                            cb_xpath = "//input[@name='KEYWORD_LVL' and @value='3']" # XPathは要確認
                            cb = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, cb_xpath)))
                            if cb.is_selected(): # チェックが入っていたら
                                if not click_element(driver, cb): # クリックして外す
                                    print("      [警告] 学年「3年」チェックボックスのクリックに失敗しました。")
                                time.sleep(0.5) # クリック後の待機
                        except TimeoutException:
                            pass # チェックボックスがなければ何もしない
                        except Exception as e_cb:
                            print(f"      学年「3年」チェックボックスの処理中にエラー: {e_cb}")

                        # 検索ボタンをクリック
                        search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(), '検索')]" # XPathは要確認
                        search_button = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                        if not click_element(driver, search_button):
                            # 検索ボタンクリック失敗時はこの年度をスキップ
                            print("    [エラー] 検索ボタンのクリックに失敗しました。この年度をスキップします。")
                            save_screenshot(driver, f"search_button_click_failed_{year}", screenshots_dir)
                            year_index += 1; continue

                        # 検索結果が表示されるか、「該当なし」メッセージが表示されるまで待機
                        # (どちらかの要素が現れるまで待つ)
                        result_indicator_xpath = "//a[contains(@class, 'syllabus-detail')] | //div[contains(text(), '該当するデータはありません')]"
                        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                        time.sleep(SHORT_WAIT) # 結果表示後の待機

                        # 「該当するデータはありません」メッセージが表示されているか確認
                        try:
                            no_result_element = driver.find_element(By.XPATH, "//div[contains(text(), '該当するデータはありません')]")
                            if no_result_element.is_displayed(): # 要素が存在し、表示されているか
                                print(f"  [情報] {year}年度、分野 '{field_name}' に該当するシラバスはありませんでした。")
                                year_index += 1; continue # 次の年度へ
                        except NoSuchElementException:
                            pass # 結果あり、処理を続行

                        # 検索結果の表示順を「科目名順」に変更 (必要に応じて調整)
                        try:
                            sort_xpath = "//select[@name='SEARCH_RESULT_NARABIJUN']" # XPathは要確認
                            sort_element = WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, sort_xpath)))
                            if not select_option_by_text(driver, sort_element, "科目名順"):
                                # テキストでの選択が失敗した場合、valueでの選択を試みる (value='2'が科目名順と仮定)
                                try:
                                    Select(sort_element).select_by_value("2")
                                    time.sleep(SHORT_WAIT)
                                except Exception:
                                    print(f"      [警告] Value='2'での表示順設定に失敗しました。")
                                    # JavaScriptでの設定も試みる
                                    try:
                                        driver.execute_script("arguments[0].value = '2'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", sort_element)
                                        time.sleep(SHORT_WAIT)
                                    except Exception as e_js:
                                        print(f"      [警告] JavaScriptによる表示順設定も失敗: {e_js}")
                            time.sleep(SHORT_WAIT) # ソート適用後の待機
                        except TimeoutException:
                            pass # ソート要素がなければ何もしない
                        except Exception as e_sort:
                            print(f"  [警告] 表示順の設定中にエラー: {e_sort}")

                        # --- ページネーション処理 ---
                        current_page = 1
                        while True: # ページが続く限りループ
                            # print(f"    --- ページ {current_page} を処理中 ---") # Log suppressed

                            # --- ページ処理開始前にセッションタイムアウトチェック ---
                            if check_session_timeout(driver, screenshots_dir):
                                print("ページネーション中にセッションタイムアウト検出。年度処理を中断します。")
                                year_processed_successfully = False # 年度失敗フラグ
                                break # while True (ページネーションループ) を抜ける

                            # --- 現在ページのシラバス詳細へのリンクを取得 ---
                            syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]" # XPathは要確認
                            urls_on_page = []
                            try:
                                # リンクが表示されるまで待機
                                WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, syllabus_link_xpath)))
                                # 全てのリンク要素を取得し、href属性（URL）をリストに格納
                                current_links = driver.find_elements(By.XPATH, syllabus_link_xpath)
                                urls_on_page = [link.get_attribute("href") for link in current_links if link.get_attribute("href")] # href属性が存在するもののみ
                                urls_on_page = [url.strip() for url in urls_on_page if url] # 空のURLを除外
                                if not urls_on_page:
                                    # リンクが見つからない場合はページネーション終了と判断
                                    # print(f"    ページ {current_page} にシラバスリンクが見つかりません。ページネーション終了の可能性があります。") # Log suppressed
                                    break # while True (ページネーションループ) を抜ける
                            except TimeoutException:
                                # リンク待機中にタイムアウトした場合
                                print(f"    ページ {current_page} のシラバスリンク待機中にタイムアウトしました。")
                                if current_page > 1:
                                    print("    最終ページか、ページの読み込みに問題が発生した可能性があります。ページネーションを終了します。")
                                else:
                                    # 最初のページでタイムアウトした場合、結果がないか構造が違う可能性
                                    print("    最初のページでリンクが見つかりませんでした。検索結果がないか、ページの構造が想定と異なる可能性があります。")
                                break # while True (ページネーションループ) を抜ける
                            except Exception as e:
                                # その他のリンク取得エラー
                                print(f"  [エラー] ページ {current_page} のリンク取得中にエラー: {e}")
                                save_screenshot(driver, f"link_retrieval_error_p{current_page}_{year}", screenshots_dir)
                                break # while True (ページネーションループ) を抜ける
                            # print(f"    ページ {current_page} で {len(urls_on_page)} 件のリンクを検出。") # Log suppressed

                            # --- 各リンク（シラバス詳細ページ）を処理 ---
                            main_window = driver.current_window_handle # メインウィンドウのハンドルを保持
                            processed_count_on_page = 0 # このページで処理した新規シラバス数

                            for index, syllabus_url in enumerate(urls_on_page):
                                # この年度・分野で既に処理済みのURLはスキップ
                                if syllabus_url in opened_links_this_year_field:
                                    continue

                                try:
                                    # --- 詳細ページを開く前にセッションタイムアウトチェック ---
                                    if check_session_timeout(driver, screenshots_dir):
                                        print("詳細情報取得直前にセッションタイムアウト検出。年度処理を中断します。")
                                        year_processed_successfully = False # 年度失敗フラグ
                                        break # for ループ (URL処理) を抜ける

                                    # --- 新しいタブで詳細ページを開く ---
                                    initial_handles = set(driver.window_handles) # 現在のウィンドウハンドル一覧を取得
                                    # JavaScriptで新しいタブを開く
                                    driver.execute_script(f"window.open('{syllabus_url}', '_blank');")
                                    # 新しいタブが開くまで待機 (ウィンドウハンドルの数が変わるまで)
                                    WebDriverWait(driver, MEDIUM_WAIT).until(lambda d: set(d.window_handles) - initial_handles)
                                    # 新しいタブのハンドルを取得 (差分セットから取得)
                                    new_handle = list(set(driver.window_handles) - initial_handles)[0]
                                    # 新しいタブに切り替え
                                    driver.switch_to.window(new_handle)
                                    time.sleep(SHORT_WAIT) # タブ切り替え後の待機

                                    # --- ★★★ 詳細情報取得と必須データチェック ★★★ ---
                                    syllabus_details = None # 初期化
                                    try:
                                        # 詳細情報取得関数を呼び出し (内部で MissingCriticalDataError が発生する可能性あり)
                                        syllabus_details = get_syllabus_details(driver, year, screenshots_dir)
                                    finally:
                                        # --- タブ閉じ＆メインウィンドウ戻り (エラー発生時も確実に実行) ---
                                        current_handle = driver.current_window_handle # 閉じる前のハンドル取得 (エラーで変わっている可能性も考慮)
                                        if current_handle != main_window:
                                            # 現在のウィンドウがメインウィンドウでなければ閉じる
                                            try:
                                                driver.close() # 現在のタブ (詳細ページ) を閉じる
                                            except NoSuchWindowException:
                                                # タイミングによっては既に閉じられている場合がある
                                                print(f"      [警告] タブ ({current_handle[-6:]}) を閉じようとしましたが、既に存在しませんでした。")
                                            except Exception as close_err:
                                                print(f"      [警告] タブ ({current_handle[-6:]}) を閉じる際にエラー: {close_err}")
                                        else:
                                            # 何らかの理由でメインウィンドウにいる場合は閉じない (予期せぬ状況)
                                            print(f"      [警告] 現在ウィンドウ({current_handle[-6:]})がメインウィンドウ({main_window[-6:]})と同じため閉じません。")

                                        # メインウィンドウに戻る試行
                                        try:
                                            # ハンドルが存在するか確認してから切り替える
                                            if main_window in driver.window_handles:
                                                driver.switch_to.window(main_window)
                                                time.sleep(0.3) # メインウィンドウに戻った後少し待つ
                                            else:
                                                # メインウィンドウが既に存在しない場合
                                                print(f"  [エラー] メインウィンドウ ({main_window[-6:]}) が既に存在しません。年度処理中断。")
                                                year_processed_successfully = False
                                                raise NoSuchWindowException(f"Main window handle {main_window} not found.")
                                        except NoSuchWindowException:
                                            # メインウィンドウに戻れない = 致命的な状況
                                            print(f"  [エラー] メインウィンドウ ({main_window[-6:]}) に戻れませんでした。ウィンドウが閉じられた可能性があります。年度処理中断。")
                                            year_processed_successfully = False # 年度失敗フラグ
                                            raise # 上位のexcept (年度ループのexcept) で捕捉させる

                                    # --- 取得結果の処理 ---
                                    if syllabus_details:
                                        # 成功した場合、データをリストに追加し、処理済みURLセットに追加
                                        scraped_data_all_years.append(syllabus_details)
                                        opened_links_this_year_field.add(syllabus_url)
                                        processed_count_on_page += 1
                                        # ★★★★★ 成功ログ ★★★★★
                                        course_name_log = syllabus_details.get('name_ja', '名称不明')
                                        course_id_log = syllabus_details.get('course_id', 'ID不明')
                                        print(f"      [成功] コース処理完了: {course_name_log} (ID: {course_id_log}, 年度: {year}, 分野: {field_name})")
                                        # ★★★★★★★★★★★★★★★★★★★★★
                                    # else:
                                        # get_syllabus_details が None を返した場合 (内部でエラーログ出力済み)
                                        # この場合、MissingCriticalDataErrorが発生していなければ処理は続行されるが、
                                        # Stricter checkにより、Noneが返るケースは減るはず。
                                        pass

                                # --- ★★★ MissingCriticalDataError 捕捉とスクリプト終了 ★★★ ---
                                except MissingCriticalDataError as e_critical:
                                    # get_syllabus_details で必須データまたは定義済みデータが取得できなかった場合
                                    print(f"\n[!!!] データ欠落が検出されたため、処理を緊急停止します: {e_critical}")
                                    save_screenshot(driver, "critical_data_missing", screenshots_dir)
                                    sys.exit(1) # ★ スクリプトを終了コード1で停止

                                except TimeoutException as e_tab:
                                    # 新しいタブの処理中にタイムアウトした場合
                                    print(f"      [警告] 新しいタブの処理中にタイムアウトが発生しました: {e_tab}。このシラバスをスキップします。")
                                    save_screenshot(driver, f"tab_open_timeout_{year}_p{current_page}", screenshots_dir)
                                    # タブ閉じとメインウィンドウへの復帰は上の finally ブロックで試行される

                                except NoSuchWindowException as e_win:
                                    # ウィンドウ/タブが予期せず閉じた場合
                                    print(f"    [エラー] ウィンドウが消失しました ({e_win})。年度処理を中断します。")
                                    year_processed_successfully = False # 年度失敗フラグ
                                    raise # 上位のexcept (年度ループのexcept) で捕捉させる

                                except (InvalidSessionIdException) as e_session:
                                    # セッションが無効になった場合
                                    print(f"    [エラー] セッションエラーが発生しました ({e_session})。年度処理を中断します。")
                                    year_processed_successfully = False # 年度失敗フラグ
                                    raise # 上位のexcept (年度ループのexcept) で捕捉させる

                                except Exception as e_detail:
                                    # その他の予期せぬエラー
                                    print(f"      [エラー] 個別シラバスの処理中に予期せぬエラーが発生しました: {e_detail}")
                                    save_screenshot(driver, f"detail_unknown_error_{year}_p{current_page}", screenshots_dir)
                                    traceback.print_exc()
                                    # このシラバスはスキップするが、処理は続行 (タブ閉じ等はfinallyで行われる)

                                # forループ内で年度失敗フラグが立ったら、それ以上URL処理を行わない
                                if not year_processed_successfully:
                                    break

                            # forループ(URL処理)が中断された場合、ページネーションループも抜ける
                            if not year_processed_successfully:
                                break
                            # print(f"    ページ {current_page} で {processed_count_on_page} 件の新規シラバスを処理しました。") # Log suppressed

                            # --- 次ページへの遷移処理 ---
                            try:
                                # 「次へ」ボタンのXPath (disabledクラスが付いていないものを探す)
                                next_xpath = "//li[not(contains(@class, 'disabled'))]/a[contains(text(), '次') or contains(., 'Next')]"
                                # 次へボタンがクリック可能になるまで待機
                                next_button = WebDriverWait(driver, MEDIUM_WAIT).until(EC.element_to_be_clickable((By.XPATH, next_xpath)))
                                # 次へボタンをクリック
                                if click_element(driver, next_button):
                                    current_page += 1 # ページ番号をインクリメント
                                    # 次のページの検索結果表示を待つ (result_indicator_xpath は検索結果リンク or 該当なしメッセージ)
                                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                    time.sleep(SHORT_WAIT) # ページ遷移後の待機
                                else:
                                    # click_element が False を返した場合
                                    print("    [警告] 次ページボタンのクリックに失敗しました。ページネーションを終了します。")
                                    save_screenshot(driver, f"next_page_click_failed_p{current_page}_{year}", screenshots_dir)
                                    break # while True (ページネーションループ) を抜ける
                            except TimeoutException:
                                # 次へボタンが見つからない = 最終ページ
                                print(f"    次ページボタンが見つかりません。最終ページ ({current_page}) と判断します。")
                                break # while True (ページネーションループ) を抜ける
                            except StaleElementReferenceException:
                                # 次へボタンが古くなった場合
                                print("    [警告] 次ページボタンがStaleになりました。ページネーションを終了します。")
                                save_screenshot(driver, f"next_page_stale_p{current_page}_{year}", screenshots_dir)
                                break # while True (ページネーションループ) を抜ける
                            except Exception as e_page:
                                # その他のページネーションエラー
                                print(f"  [エラー] ページネーション中にエラーが発生しました: {e_page}")
                                save_screenshot(driver, f"pagination_error_p{current_page}_{year}", screenshots_dir)
                                break # while True (ページネーションループ) を抜ける

                        # --- 年度ループ内の try ブロック終了 ---
                        # この年度の処理が中断されずに完了した場合
                        if year_processed_successfully:
                            print(f"--- {year}年度 (分野: {field_name}) の処理が正常に終了しました ---")
                            year_index += 1 # 次の年度へ
                        else:
                            # 年度処理が失敗した場合 (セッションエラー等で中断された場合)
                            print(f"--- {year}年度 (分野: {field_name}) の処理が中断されました ---")
                            # この例外を発生させ、上位のexceptでWebDriver再起動を試みる
                            raise Exception(f"年度 {year} の処理が中断されました。WebDriver再起動を試みます。")

                    # --- 年度ループ内の except ブロック ---
                    except (InvalidSessionIdException, NoSuchWindowException) as e_session_year:
                        # 回復不能なセッション/ウィンドウエラーが発生した場合
                        print(f"\n[!!!] 年度 {year} の処理中にセッション/ウィンドウエラーが発生しました: {e_session_year}。WebDriverの再起動を試みます。")
                        save_screenshot(driver, f"year_session_error_{year}", screenshots_dir)
                        # WebDriverを終了して再初期化
                        if driver:
                            try:
                                driver.quit()
                            except Exception as quit_err_year:
                                print(f"      WebDriver終了時にエラー(年度ループ内): {quit_err_year}")
                            driver = None # quit後はNoneにする
                        driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                        if not driver:
                            # 再初期化に失敗したら処理中断
                            raise Exception("WebDriverの再初期化に失敗しました。処理を中断します。")
                        # 再ログイン試行
                        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                            # 再ログインに失敗したら処理中断
                            raise Exception("再ログインに失敗しました。処理を中断します。")
                        print(f"      WebDriverの再起動と再ログインが完了しました。年度 {year} (インデックス: {year_index}) の処理を再試行します。")
                        # year_index をインクリメントせずに continue し、現在の年度を再試行
                        continue # while year_index < len(TARGET_YEARS) ループの最初から再試行

                    except Exception as e_year_main:
                        # 年度レベルでのその他の予期せぬエラー
                        print(f"  [エラー] {year}年度の処理中に予期せぬエラーが発生しました: {e_year_main}")
                        save_screenshot(driver, f"year_main_unknown_error_{year}", screenshots_dir)
                        traceback.print_exc()
                        print("      この年度をスキップして次の年度に進みます。")
                        year_index += 1 # エラーが発生した年度をスキップして次の年度へ

                # --- 分野ループ内の try ブロック終了 ---
                # この分野の全ての年度が正常に処理された場合 (途中でスキップされた場合も含む)
                print(f"===== 分野: {field_name} の全年度処理が完了しました =====")
                field_index += 1 # 次の分野へ

            # --- 分野ループ内の except ブロック ---
            except (InvalidSessionIdException, NoSuchWindowException) as e_session_field:
                # 回復不能なセッション/ウィンドウエラーが発生した場合
                print(f"\n[!!!] 分野 '{field_name}' の処理中にセッション/ウィンドウエラーが発生しました: {e_session_field}。WebDriverの再起動を試みます。")
                save_screenshot(driver, f"field_session_error_{field_name}", screenshots_dir)
                # WebDriverを終了して再初期化
                if driver:
                    try:
                        driver.quit()
                    except Exception as quit_err_field:
                         print(f"      WebDriver終了時にエラー(分野ループ内): {quit_err_field}")
                    driver = None # quit後はNoneにする
                driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                if not driver:
                    # 再初期化に失敗したら処理中断
                    raise Exception("WebDriverの再初期化に失敗しました。処理を中断します。")
                # 再ログイン試行
                if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                    # 再ログインに失敗したら処理中断
                    raise Exception("再ログインに失敗しました。処理を中断します。")
                print(f"      WebDriverの再起動と再ログインが完了しました。分野 '{field_name}' (インデックス: {field_index}) の処理を再試行します。")
                # field_index をインクリメントせずに continue し、現在の分野を再試行
                continue # while field_index < len(TARGET_FIELDS) ループの最初から再試行

            except Exception as e_field_main:
                # 分野レベルでのその他の予期せぬエラー
                print(f"  [エラー] 分野 '{field_name}' の処理中に予期せぬエラーが発生しました: {e_field_main}")
                save_screenshot(driver, f"field_main_unknown_error_{field_name}", screenshots_dir)
                traceback.print_exc()
                print("      この分野をスキップして次の分野に進みます。")
                field_index += 1 # エラーが発生した分野をスキップして次の分野へ
            # finally: print(f"===== 分野: {field_name} の処理ブロック終了 =====") # Log suppressed

    # --- グローバル try ブロック終了 ---
    except KeyboardInterrupt:
        # Ctrl+C などで中断された場合
        print("\nキーボード割り込みにより処理を中断しました。")
    except SystemExit as e:
        # sys.exit() が呼び出された場合 (MissingCriticalDataError などで意図的に停止)
        print(f"\nスクリプトが意図的に停止されました (終了コード: {e.code})。")
    except Exception as e_global:
        # どこでも捕捉されなかった最終的なエラー
        print(f"\n★★★ 予期せぬ重大エラーが発生したため、処理を中断します: {e_global} ★★★")
        traceback.print_exc()
        # エラー発生時のスクリーンショットを試みる
        if driver:
            try:
                save_screenshot(driver, "fatal_error", screenshots_dir)
            except Exception as ss_err:
                print(f"      最終エラー時のスクリーンショット保存失敗: {ss_err}")
    finally:
        # --- 終了処理 (エラー発生有無に関わらず実行) ---
        # WebDriverが起動していれば閉じる
        if driver:
            try:
                driver.quit() # ブラウザの全ウィンドウを閉じてプロセスを終了
                print("\nブラウザを閉じました。")
            except Exception as qe:
                # quit中にエラーが発生しても、特に何もせず終了させる
                print(f"\nブラウザ終了時にエラーが発生しました: {qe}")

        print("\n=== 最終処理 ===")
        # 収集したデータがあれば集約してJSONファイルに保存
        if scraped_data_all_years:
            print(f"合計 {len(scraped_data_all_years)} 件の生データを取得しました。")
            print("\nデータを集約しています...")
            final_json_data = aggregate_syllabus_data(scraped_data_all_years) # データ集約関数を呼び出し
            if final_json_data:
                print(f"集約後のデータ件数: {len(final_json_data)}")
                print(f"\n最終データを '{output_json_path}' に書き込んでいます...")
                try:
                    # JSONファイルに書き込み (UTF-8エンコーディング, ensure_ascii=Falseで日本語をそのまま出力, indent=4で見やすく整形)
                    with open(output_json_path, mode='w', encoding='utf-8') as f:
                        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
                    print(f"JSONファイル書き込み完了。")
                except Exception as e:
                    print(f"[エラー] JSONファイル書き込み中にエラーが発生しました: {e}")
            else:
                # 集約後のデータが空の場合
                print("集約後のデータがありません。JSONファイルは作成されませんでした。")
        else:
            # 生データが一件も収集されなかった場合
            print("\n有効なデータが収集されませんでした。")

        # 処理時間計測と終了時刻表示
        end_time = time.time()
        elapsed_time = end_time - global_start_time # 経過時間を計算
        print(f"\n処理時間: {elapsed_time:.2f} 秒") # 小数点以下2桁で表示
        print(f"スクレイピング終了: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")