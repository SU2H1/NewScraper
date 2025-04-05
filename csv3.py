# -*- coding: utf-8 -*-
# --- ライブラリインポート ---
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
CHROME_DRIVER_PATH = None
USER_EMAIL = 'kaitosumishi@keio.jp'
USER_PASSWORD = '0528QBSkaito' # ★★★ パスワード確認 ★★★
OUTPUT_DIR_NAME = 'syllabus_output'
OUTPUT_JSON_FILE = 'syllabus_data.json'
TARGET_FIELDS = ["基盤科目", "先端科目", "特設科目"]
TARGET_YEARS = [2025, 2024, 2023]
HEADLESS_MODE = False
PAGE_LOAD_TIMEOUT = 45
ELEMENT_WAIT_TIMEOUT = 25
SHORT_WAIT = 3
MEDIUM_WAIT = 5
LONG_WAIT = 10

# --- ★ カスタム例外クラス ★ ---
class MissingCriticalDataError(Exception):
    """必須データが取得できなかった場合に発生させる例外"""
    pass

# --- ヘルパー関数 (変更なし、ただしログ抑制のため一部printをコメントアウト) ---

def create_output_dirs(base_dir=OUTPUT_DIR_NAME):
    logs_dir = os.path.join(base_dir, "logs")
    screenshots_dir = os.path.join(base_dir, "screenshots")
    for dir_path in [base_dir, logs_dir, screenshots_dir]:
        os.makedirs(dir_path, exist_ok=True)
    return base_dir, logs_dir, screenshots_dir

def save_screenshot(driver, prefix="screenshot", dir_path="screenshots"):
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
        print(f"[エラー] スクリーンショットの保存に失敗: {e}")
    except Exception as e:
        print(f"[エラー] スクリーンショット保存中に予期せぬエラー: {e}")
    return None

def normalize_text(text):
    if isinstance(text, str):
        text = text.replace('　', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    return ""

def click_element(driver, element, wait_time=SHORT_WAIT):
    try:
        WebDriverWait(driver, wait_time).until(EC.element_to_be_clickable(element))
        element.click()
        time.sleep(0.3)
        return True
    except ElementClickInterceptedException:
        # print("      通常のClickが妨害されたため、JavaScriptでClickを試みます。") # Log suppressed
        try:
            driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.3)
            return True
        except Exception as js_e:
            print(f"      JavaScript Click中にエラー: {js_e}")
            return False
    except StaleElementReferenceException:
        print("      Click試行中に要素がStaleになりました。再取得が必要です。")
        return False
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
         print(f"      Click中にセッション/ウィンドウエラー: {e_session}")
         raise
    except Exception as e:
        print(f"      Click中に予期せぬエラー: {e}")
        return False

def select_option_by_text(driver, select_element, option_text, fallback_to_js=True):
    try:
        select_obj = Select(select_element)
        select_obj.select_by_visible_text(option_text)
        time.sleep(0.3)
        selected_option = Select(select_element).first_selected_option
        if selected_option.text.strip() == option_text:
             return True
        else:
             # print(f"    [警告] select_by_visible_text後、選択値が '{selected_option.text.strip()}' となり期待値 '{option_text}' と異なります。") # Log suppressed
             raise Exception("Selection did not reflect correctly.")
    except Exception as e:
        # print(f"    通常の select_by_visible_text 失敗: {e}") # Log suppressed
        if fallback_to_js:
            try:
                js_script = f"""
                    let select = arguments[0]; let optionText = arguments[1];
                    for(let i = 0; i < select.options.length; i++) {{
                        if(select.options[i].text.trim() === optionText) {{
                            select.selectedIndex = i;
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            select.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true; }} }} return false; """
                result = driver.execute_script(js_script, select_element, option_text)
                if result:
                    time.sleep(0.5)
                    selected_option_text_js = driver.execute_script("return arguments[0].options[arguments[0].selectedIndex].text.trim();", select_element)
                    if selected_option_text_js == option_text:
                        return True
                    else:
                        # print(f"    [警告] JavaScriptでの選択後も値が期待通りではありません (現在値: '{selected_option_text_js}')。") # Log suppressed
                        return False
                else:
                    # print(f"    JavaScriptによる選択も失敗: '{option_text}' が見つかりません。") # Log suppressed
                    return False
            except (InvalidSessionIdException, NoSuchWindowException) as e_session:
                 print(f"      JS選択中にセッション/ウィンドウエラー: {e_session}")
                 raise
            except Exception as js_error:
                print(f"    JavaScriptによる選択中にエラー: {js_error}")
                return False
        else:
            return False

# --- ★★★ get_syllabus_details 関数の修正 ★★★ ---
def get_syllabus_details(driver, current_year, screenshots_dir):
    """
    シラバス詳細ページから情報を取得。
    必須情報が欠落していたら MissingCriticalDataError を発生させる。
    """
    details = {'year_scraped': current_year}
    current_url = "N/A"
    try:
        current_url = driver.current_url
        # --- ページの主要要素が表示されるまで待機 ---
        # ★★★ 要調査: 実際の詳細ページの「科目名」や主要な表などが含まれる要素で待機 ★★★
        WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[@class='page-title']/h2 | //table[contains(@class, 'syllabus')] | //div[@id='contents']") # より具体的な要素候補
            )
        )
    except TimeoutException:
        print(f"  [エラー] 詳細ページの読み込みタイムアウト。 URL: {current_url}")
        save_screenshot(driver, f"detail_load_timeout_{current_year}", screenshots_dir)
        return None # タイムアウトは続行不能としてNoneを返す
    except (InvalidSessionIdException, NoSuchWindowException) as e_session:
         print(f"  [エラー] 詳細ページ読み込み中にセッション/ウィンドウエラー: {e_session}")
         raise # ★ このエラーは上位で処理
    except WebDriverException as e:
        print(f"  [エラー] 詳細ページ読み込み中にWebDriverエラー: {e} URL: {current_url}")
        save_screenshot(driver, f"detail_load_error_{current_year}", screenshots_dir)
        return None
    except Exception as e:
        print(f"  [エラー] 詳細ページ読み込み中に予期せぬエラー: {e} URL: {current_url}")
        save_screenshot(driver, f"detail_load_unknown_error_{current_year}", screenshots_dir)
        return None

    # --- Course ID 取得 ---
    details['course_id'] = None
    # (Course ID取得ロジックは変更なし)
    try:
        id_match = re.search(r'[?&]id=(\d+)', current_url) or \
                   re.search(r'/syllabus/(\d+)', current_url) or \
                   re.search(r'[?&]entno=(\d+)', current_url)
        if id_match: details['course_id'] = id_match.group(1)
        else:
            try:
                 hidden = driver.find_element(By.XPATH, "//input[@type='hidden' and (contains(@name, 'id') or contains(@name, 'entno'))]")
                 if hidden.get_attribute('value').isdigit(): details['course_id'] = hidden.get_attribute('value')
            except NoSuchElementException: pass
        # if not details['course_id']: print(f"  [警告] Course ID が取得できませんでした。 URL: {current_url}") # Log suppressed
    except Exception as e: print(f"  [警告] Course ID の取得中にエラー: {e}")

    # --- 各情報の取得 ---
    # ★★★ XPathは実際のHTMLに合わせて【必ず】修正してください ★★★
    info_map = {
        # --- 必須項目 (これらが取得できない、または不適切な場合はエラーとする) ---
        'name_ja': ("科目名", "//div[@class='page-title']/h2", f"名称不明-{details.get('course_id', 'ID不明')}", By.XPATH), # ←★★★【要修正】★★★
        'semester_ja': ("学期", "//tr[th[normalize-space()='開講学期・クラス']]/td", "学期不明"), # ←★★★【要修正】★★★
        # --- オプショナル項目 ---
        'professor_ja': ("担当者名", "//tr[th[contains(text(),'担当者名')]]/td", ""),
        'credits_ja': ("単位", "//tr[th[contains(text(),'単位')]]/td", "単位不明"),
        'field_ja': ("分野", "//tr[th[contains(text(),'分野')]]/td", "分野不明"),
        'location_ja': ("教室", "//tr[th[contains(text(),'教室')]]/td", "教室不明"),
        'day_period_ja': ("曜日時限", "//tr[th[contains(text(),'曜日時限')]]/td", "曜日時限不明"),
    }

    # ★ 不適切と判断する科目名のパターン（ページのタイトルなど）
    INVALID_COURSE_NAME_PATTERNS = ["慶應義塾大学 シラバス・時間割"]

    # --- 必須情報フラグ ---
    critical_data_missing = False
    missing_details = []

    for key, (label, xpath, default_value, *find_by) in info_map.items():
        by_method = find_by[0] if find_by else By.XPATH
        try:
            element = driver.find_element(by_method, xpath)
            details[key] = normalize_text(element.text)
            if not details[key]: details[key] = default_value

            # --- ★ 必須情報のチェック ★ ---
            # 1. 科目名チェック
            if key == 'name_ja':
                # デフォルト値、または不適切パターンに含まれる場合はエラー
                if details[key] == default_value or any(pattern in details[key] for pattern in INVALID_COURSE_NAME_PATTERNS):
                    critical_data_missing = True
                    missing_details.append(f"{label}: 取得値「{details[key]}」が不適切 (XPath: {xpath})")
                    details[key] = default_value # 値をデフォルトに戻す

            # 2. 学期チェック
            elif key == 'semester_ja':
                if details[key] == default_value:
                    critical_data_missing = True
                    missing_details.append(f"{label}: 見つかりません (XPath: {xpath})")

        except NoSuchElementException:
            details[key] = default_value
            # ★ 必須情報が見つからない場合もエラー
            if key in ['name_ja', 'semester_ja']:
                critical_data_missing = True
                missing_details.append(f"{label}: 要素が見つかりません (XPath: {xpath})")
        except StaleElementReferenceException:
             details[key] = default_value
             print(f"  [警告] {label} ({xpath}) の取得中に要素がStaleになりました。デフォルト値「{default_value}」を使用。")
             # Staleの場合は必須項目でも今回はエラーにしない（再試行で取得できる可能性があるため）
        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
             print(f"  [エラー] {label} 取得中にセッション/ウィンドウエラー: {e_session}")
             raise # ★ 上位で処理
        except Exception as e:
            details[key] = default_value
            print(f"  [警告] {label} ({xpath}) の取得中にエラー: {e}。デフォルト値「{default_value}」を使用。")
            # 不明なエラーの場合も必須項目ならエラーにするか検討（今回はしない）

    # --- ★ 必須データ欠落があれば例外発生 ---
    if critical_data_missing:
        error_message = f"必須データの取得に失敗しました (URL: {current_url}): {'; '.join(missing_details)}"
        print(f"  [エラー] {error_message}")
        raise MissingCriticalDataError(error_message) # ★ スクリプト停止のために例外を発生

    # --- 英語情報の仮設定 (変更なし) ---
    details['professor_en'] = details.get('professor_ja', '')
    details['name_en'] = details.get('name_ja', '')
    details['credits_en'] = details.get('credits_ja', '')
    details['field_en'] = details.get('field_ja', '')
    details['location_en'] = details.get('location_ja', '')
    details['semester_en'] = details.get('semester_ja', '')
    details['day_period_en'] = details.get('day_period_ja', '')
    # (英語変換ロジックは変更なし)
    try:
        sem_elem = driver.find_element(By.XPATH, "//tr[th[normalize-space()='開講学期・クラス']]/td") # ←★★★【要修正】★★★
        en_sem = sem_elem.get_attribute('data-en-value')
        if en_sem: details['semester_en'] = normalize_text(en_sem)
        else:
             sem_map = {"春学期": "Spring", "秋学期": "Fall", "通年": "Full Year"}
             ja_sem = normalize_text(sem_elem.text).split()[0]
             if ja_sem in sem_map: details['semester_en'] = sem_map[ja_sem]
    except: pass
    try:
        dp_elem = driver.find_element(By.XPATH, "//tr[th[contains(text(),'曜日時限')]]/td")
        en_dp = dp_elem.get_attribute('data-en-value')
        if en_dp: details['day_period_en'] = normalize_text(en_dp)
        else:
            ja_dp = details.get('day_period_ja', '')
            day_map = {"月": "Mon", "火": "Tue", "水": "Wed", "木": "Thu", "金": "Fri", "土": "Sat", "日": "Sun"}
            parts = ja_dp.split()
            if len(parts) >= 2 and parts[0] in day_map: details['day_period_en'] = f"{day_map[parts[0]]} {' '.join(parts[1:])}"
    except: pass

    # print(f"      ✓ 詳細情報取得完了: 「{details.get('name_ja', '不明')}」") # ログ抑制
    return details

# --- aggregate_syllabus_data 関数 (変更なし) ---
def aggregate_syllabus_data(all_raw_data):
    if not all_raw_data: return []
    grouped_by_key = {}
    skipped_count = 0
    for item in all_raw_data:
        course_id = item.get('course_id')
        if not course_id: skipped_count += 1; continue
        professors_str = item.get('professor_ja', '')
        professors = tuple(sorted([p.strip() for p in professors_str.split('/') if p.strip()]))
        semester_en = item.get('semester_en', item.get('semester_ja', 'unknown'))
        if not semester_en or semester_en in ["学期不明", "曜日時限不明"]: semester_en = "unknown"
        agg_key = (course_id, professors, semester_en)
        if agg_key not in grouped_by_key: grouped_by_key[agg_key] = []
        grouped_by_key[agg_key].append(item)
    if skipped_count > 0: print(f"ID不足により {skipped_count} 件のデータが集約からスキップされました。")
    final_list = []
    for agg_key, year_data_list in grouped_by_key.items():
        year_data_list.sort(key=lambda x: x['year_scraped'], reverse=True)
        latest_data = year_data_list[0]
        years_scraped = sorted(list(set(d['year_scraped'] for d in year_data_list)))
        day_period_ja = latest_data.get('day_period_ja', '曜日時限不明')
        day_period_en = latest_data.get('day_period_en', 'unknown')
        location_ja = latest_data.get('location_ja', '教室不明')
        location_en = latest_data.get('location_en', 'unknown')
        aggregated_item = {
            "course_id": latest_data['course_id'], "year": "、".join(map(str, years_scraped)),
            "semester": semester_en, "day_period": day_period_en,
            "professor_ja": latest_data.get('professor_ja', ''),
            "translations": {
                "ja": {"name": latest_data.get('name_ja', ''), "field": latest_data.get('field_ja', ''), "credits": latest_data.get('credits_ja', ''), "semester": latest_data.get('semester_ja', ''), "day_period": day_period_ja, "location": location_ja, },
                "en": {"name": latest_data.get('name_en', ''), "field": latest_data.get('field_en', ''), "credits": latest_data.get('credits_en', ''), "semester": semester_en, "day_period": day_period_en, "location": location_en, } } }
        final_list.append(aggregated_item)
    return final_list

# --- login 関数 (変更なし) ---
def login(driver, email, password, screenshots_dir):
    login_url = 'https://gslbs.keio.jp/syllabus/search'
    max_login_attempts = 2
    for attempt in range(max_login_attempts):
        print(f"\nログイン試行 {attempt + 1}/{max_login_attempts}...")
        try:
            # print(f"ログインページにアクセス: {login_url}") # Log suppressed
            driver.get(login_url)
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @name='identifier']")))
            time.sleep(SHORT_WAIT)
            username_field = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='email' or @name='identifier']")))
            username_field.clear(); username_field.send_keys(email); time.sleep(0.5)
            next_button_selectors = ["//button[contains(., 'Next')]", "//button[contains(., '次へ')]", "//button[@type='submit']", "//input[@type='submit' and (contains(@value, 'Next') or contains(@value, '次へ'))]", "//div[@role='button' and (contains(., 'Next') or contains(., '次へ'))]" ]
            next_button = None
            for selector in next_button_selectors:
                try:
                    next_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    if click_element(driver, next_button): break
                    else: next_button = None
                except TimeoutException: continue
                except StaleElementReferenceException: time.sleep(1); continue
                except (InvalidSessionIdException, NoSuchWindowException) as e_session: raise e_session
            if not next_button:
                 # print("「次へ」ボタンが見つからないかクリックできませんでした。Enterキーを送信します...") # Log suppressed
                 try: username_field.send_keys(Keys.RETURN)
                 except Exception as e_enter: print(f"  Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_next_button_error_{attempt+1}", screenshots_dir); raise Exception("「次へ」ボタン処理失敗")
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            time.sleep(SHORT_WAIT)
            password_field = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            password_field.clear(); password_field.send_keys(password); time.sleep(0.5)
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
            if not signin_button:
                 # print("「サインイン」ボタンが見つからないかクリックできませんでした。Enterキーを送信します...") # Log suppressed
                 try: password_field.send_keys(Keys.RETURN)
                 except Exception as e_enter: print(f"  Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_signin_button_error_{attempt+1}", screenshots_dir); raise Exception("「サインイン」ボタン処理失敗")
            # print("ログイン完了と検索ページへの遷移を待ちます...") # Log suppressed
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT + LONG_WAIT).until( EC.any_of( EC.url_contains("gslbs.keio.jp/syllabus/search"), EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '検索')]")) ))
            current_url = driver.current_url
            if "gslbs.keio.jp/syllabus/search" in current_url:
                print("ログイン成功、検索ページに到達しました。")
                try:
                    search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(),'検索')]"
                    WebDriverWait(driver, MEDIUM_WAIT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                except TimeoutException: print("[警告] 検索画面の主要要素確認タイムアウト。")
                return True
            else:
                print(f"[警告] ログイン後のURLが期待した検索ページではありません。 URL: {current_url}")
                save_screenshot(driver, f"login_unexpected_page_{attempt+1}", screenshots_dir)
                if "auth" in current_url or "verify" in current_url or "duo" in current_url: print("[情報] 2段階認証?"); raise Exception("2段階認証検出")
        except (InvalidSessionIdException, NoSuchWindowException) as e_session: print(f"[エラー] ログイン処理中にセッション/ウィンドウエラー (試行 {attempt + 1}): {e_session}"); raise
        except TimeoutException as e: print(f"[エラー] ログイン処理中にタイムアウト (試行 {attempt + 1})。"); save_screenshot(driver, f"login_timeout_{attempt+1}", screenshots_dir); if attempt == max_login_attempts - 1: raise e; print("リトライします..."); time.sleep(MEDIUM_WAIT)
        except WebDriverException as e: print(f"[エラー] ログイン処理中にWebDriverエラー (試行 {attempt + 1}): {e}"); save_screenshot(driver, f"login_webdriver_error_{attempt+1}", screenshots_dir); if "net::ERR" in str(e): print("  ネットワーク接続/URL問題?"); if attempt == max_login_attempts - 1: raise e; print("リトライします..."); time.sleep(MEDIUM_WAIT)
        except Exception as e: print(f"[エラー] ログイン処理中に予期せぬエラー (試行 {attempt + 1}): {e}"); save_screenshot(driver, f"login_unknown_error_{attempt+1}", screenshots_dir); traceback.print_exc(); if attempt == max_login_attempts - 1: raise e; print("リトライします..."); time.sleep(MEDIUM_WAIT)
    print("ログインに失敗しました。"); return False

# --- check_session_timeout 関数 (変更なし) ---
def check_session_timeout(driver, screenshots_dir):
    try:
        current_url = driver.current_url; page_title = driver.title; page_source = driver.page_source.lower()
        timeout_keywords = ["セッションタイムアウト", "session timeout", "ログインし直してください", "log back in"]
        error_page_url_part = "/syllabus/appMsg"
        is_session_timeout = False
        if error_page_url_part in current_url: is_session_timeout = True
        elif any(keyword in page_source for keyword in timeout_keywords): is_session_timeout = True
        elif "error" in page_title.lower() and any(keyword in page_source for keyword in timeout_keywords): is_session_timeout = True
        if is_session_timeout: print("[警告] セッションタイムアウトページが検出されました。"); save_screenshot(driver, "session_timeout_detected", screenshots_dir); return True
        else: return False
    except (TimeoutException, StaleElementReferenceException): return False # 一時的なエラーはタイムアウトではない
    except WebDriverException as e:
         if "invalid session id" in str(e).lower() or "no such window" in str(e).lower(): raise # 上位で処理
         else: print(f"[エラー] セッションタイムアウトチェック中に予期せぬWebDriverエラー: {e}"); save_screenshot(driver, "session_check_webdriver_error", screenshots_dir); return False
    except Exception as e: print(f"[エラー] セッションタイムアウトチェック中に予期せぬエラー: {e}"); save_screenshot(driver, "session_check_unknown_error", screenshots_dir); traceback.print_exc(); return False

# --- initialize_driver 関数 (変更なし) ---
def initialize_driver(driver_path, headless=False):
    print("\nWebDriverを初期化しています...")
    options = webdriver.ChromeOptions(); options.page_load_strategy = 'normal'
    if headless: options.add_argument('--headless'); options.add_argument('--disable-gpu'); options.add_argument('--window-size=1920,1080'); print("ヘッドレスモードで実行します。")
    options.add_argument('--disable-extensions'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage'); options.add_argument('--disable-infobars'); options.add_argument('--disable-blink-features=AutomationControlled'); options.add_experimental_option('excludeSwitches', ['enable-automation']); options.add_experimental_option('useAutomationExtension', False)
    new_driver = None
    try:
        if driver_path and os.path.exists(driver_path): service = Service(executable_path=driver_path); new_driver = webdriver.Chrome(service=service, options=options); # print(f"指定されたChromeDriverを使用: {driver_path}") # Log suppressed
        else: print("ChromeDriverパス未指定/無効のため自動検出します。"); new_driver = webdriver.Chrome(options=options)
        new_driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT); new_driver.implicitly_wait(5)
        print("WebDriverの初期化完了。")
        return new_driver
    except WebDriverException as e: print(f"[重大エラー] WebDriverの初期化失敗: {e}"); if "session not created" in str(e).lower(): print("  ChromeDriver/Chromeバージョン不一致?"); elif "executable needs to be in PATH" in str(e): print("  ChromeDriverパス問題?"); else: traceback.print_exc(); return None
    except Exception as e: print(f"[重大エラー] WebDriver初期化中に予期せぬエラー: {e}"); traceback.print_exc(); return None

# --- ★★★ メイン処理の修正 ★★★ ---
if __name__ == "__main__":
    output_dir, logs_dir, screenshots_dir = create_output_dirs(OUTPUT_DIR_NAME)
    start_time_dt = datetime.datetime.now()
    output_json_path = os.path.join(output_dir, OUTPUT_JSON_FILE)
    driver = None
    scraped_data_all_years = []
    global_start_time = time.time()
    print(f"スクレイピング開始: {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- WebDriverとログインの初期化 ---
    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
    if not driver: sys.exit("致命的エラー: WebDriverを初期化できませんでした。") # ★ エラーなら即終了
    if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
        sys.exit("致命的エラー: 初期ログインに失敗しました。") # ★ エラーなら即終了

    # --- メインループ ---
    try:
        field_index = 0
        while field_index < len(TARGET_FIELDS):
            field_name = TARGET_FIELDS[field_index]
            print(f"\n===== 分野: {field_name} (インデックス: {field_index}) の処理開始 =====")
            field_processed_successfully = False

            try:
                # --- セッションタイムアウトチェック＆再ログイン ---
                if check_session_timeout(driver, screenshots_dir):
                    print("セッションタイムアウト検出。再ログイン試行...")
                    if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                         print("[エラー] 再ログイン失敗。この分野をスキップ。"); field_index += 1; continue

                # --- 分野選択 ---
                # print(f"  分野 '{field_name}' を選択します...") # Log suppressed
                if "gslbs.keio.jp/syllabus/search" not in driver.current_url:
                    # print("  検索ページにいないため、移動します...") # Log suppressed
                    driver.get('https://gslbs.keio.jp/syllabus/search')
                    WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search"))
                    time.sleep(MEDIUM_WAIT)
                field_select_xpath = "//select[@name='KEYWORD_FLD1CD']"
                field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                if not select_option_by_text(driver, field_select_element, field_name):
                    print(f"    [警告] 分野 '{field_name}' 選択失敗。スキップ。"); save_screenshot(driver, f"field_selection_failed_{field_name}", screenshots_dir); field_index += 1; continue
                time.sleep(SHORT_WAIT)

                # --- 年度ループ ---
                year_index = 0
                while year_index < len(TARGET_YEARS):
                    year = TARGET_YEARS[year_index]
                    print(f"\n--- {year}年度 (インデックス: {year_index}) の処理開始 (分野: {field_name}) ---")
                    year_processed_successfully = False
                    opened_links_this_year_field = set()

                    try:
                        # --- セッションタイムアウトチェック＆再ログイン（＋分野再選択）---
                        if check_session_timeout(driver, screenshots_dir):
                            print("セッションタイムアウト検出。再ログイン試行...")
                            if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                                 print("[エラー] 再ログイン失敗。この年度をスキップ。"); year_index += 1; continue
                            print(f"  再ログイン成功。分野 '{field_name}' を再選択..."); time.sleep(SHORT_WAIT)
                            field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                            if not select_option_by_text(driver, field_select_element, field_name):
                                print(f"    [警告] 再ログイン後分野 '{field_name}' 再選択失敗。年度スキップ。"); year_index += 1; continue

                        # --- 年度選択と検索 ---
                        if "gslbs.keio.jp/syllabus/search" not in driver.current_url:
                            # print("  検索ページにいないため、移動し、分野を再選択します...") # Log suppressed
                            driver.get('https://gslbs.keio.jp/syllabus/search'); WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search")); time.sleep(MEDIUM_WAIT)
                            field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, field_select_xpath)))
                            if not select_option_by_text(driver, field_select_element, field_name): print(f"    [警告] ページ移動後分野 '{field_name}' 再選択失敗。年度スキップ。"); year_index += 1; continue
                        year_select_xpath = "//select[@name='KEYWORD_TTBLYR']"
                        year_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, year_select_xpath)))
                        if not select_option_by_text(driver, year_select_element, str(year)): print(f"    [警告] 年度 '{year}' 選択失敗。スキップ。"); save_screenshot(driver, f"year_selection_failed_{year}", screenshots_dir); year_index += 1; continue
                        time.sleep(SHORT_WAIT)
                        # (学年チェック外し、検索ボタンクリック、結果待機、結果なし処理、表示順変更 - 変更なし、ログ抑制)
                        try:
                            cb_xpath = "//input[@name='KEYWORD_LVL' and @value='3']"; cb = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, cb_xpath)))
                            if cb.is_selected():
                                if not click_element(driver, cb): print("      [警告] 学年「3年」クリック失敗。"); time.sleep(0.5)
                        except TimeoutException: pass; except Exception as e_cb: print(f"      学年「3年」チェックエラー: {e_cb}")
                        search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(), '検索')]"; search_button = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                        if not click_element(driver, search_button): print("    [エラー] 検索ボタンクリック失敗。年度スキップ。"); save_screenshot(driver, f"search_button_click_failed_{year}", screenshots_dir); year_index += 1; continue
                        result_indicator_xpath = "//a[contains(@class, 'syllabus-detail')] | //div[contains(text(), '該当するデータはありません')]"; WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath))); time.sleep(SHORT_WAIT)
                        try:
                            if driver.find_element(By.XPATH, "//div[contains(text(), '該当するデータはありません')]").is_displayed(): print(f"  [情報] {year}年度、分野 '{field_name}' 結果なし。"); year_index += 1; continue
                        except NoSuchElementException: pass
                        try:
                             sort_xpath = "//select[@name='SEARCH_RESULT_NARABIJUN']"; sort_element = WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, sort_xpath)))
                             if not select_option_by_text(driver, sort_element, "科目名順"):
                                 try: Select(sort_element).select_by_value("2"); time.sleep(SHORT_WAIT)
                                 except Exception: print(f"      [警告] Value='2'表示順設定失敗。"); try: driver.execute_script("arguments[0].value = '2'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", sort_element); time.sleep(SHORT_WAIT); except Exception as e_js: print(f"      [警告] JS表示順設定失敗: {e_js}")
                             time.sleep(SHORT_WAIT)
                        except TimeoutException: pass; except Exception as e_sort: print(f"  [警告] 表示順設定エラー: {e_sort}")

                        # --- ページネーション ---
                        current_page = 1
                        while True:
                            # print(f"    --- ページ {current_page} を処理中 ---") # Log suppressed

                            # --- セッションタイムアウトチェック ---
                            if check_session_timeout(driver, screenshots_dir): print("セッションタイムアウト検出。年度中断。"); year_processed_successfully = False; break

                            # --- リンク取得 ---
                            syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]"; urls_on_page = []
                            try:
                                WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, syllabus_link_xpath)))
                                current_links = driver.find_elements(By.XPATH, syllabus_link_xpath); urls_on_page = [link.get_attribute("href") for link in current_links if link.get_attribute("href")]; urls_on_page = [url.strip() for url in urls_on_page if url]
                                if not urls_on_page: break # リンクなし -> ページネーション終了
                            except TimeoutException: print(f"    ページ {current_page} リンク待機タイムアウト。"); if current_page > 1: print("    最終ページか問題発生の可能性。"); break
                            except Exception as e: print(f"   [エラー] ページ {current_page} リンク取得エラー: {e}"); save_screenshot(driver, f"link_retrieval_error_p{current_page}_{year}", screenshots_dir); break
                            # print(f"    ページ {current_page} で {len(urls_on_page)} 件のリンクを検出。") # Log suppressed

                            # --- 各リンク処理 ---
                            main_window = driver.current_window_handle; processed_count_on_page = 0
                            for index, syllabus_url in enumerate(urls_on_page):
                                if syllabus_url in opened_links_this_year_field: continue
                                try:
                                    # --- セッションタイムアウトチェック ---
                                    if check_session_timeout(driver, screenshots_dir): print("詳細取得前タイムアウト。年度中断。"); year_processed_successfully = False; break
                                    # --- 新しいタブで開く ---
                                    initial_handles = set(driver.window_handles); driver.execute_script(f"window.open('{syllabus_url}', '_blank');"); WebDriverWait(driver, MEDIUM_WAIT).until(lambda d: set(d.window_handles) - initial_handles); new_handle = list(set(driver.window_handles) - initial_handles)[0]
                                    driver.switch_to.window(new_handle); time.sleep(SHORT_WAIT)
                                    # --- ★★★ 詳細情報取得と必須データチェック ★★★ ---
                                    syllabus_details = get_syllabus_details(driver, year, screenshots_dir) # MissingCriticalDataErrorが発生する可能性あり
                                    # --- タブ閉じ＆メインウィンドウ戻り ---
                                    current_handle = driver.current_window_handle
                                    if current_handle != main_window: driver.close()
                                    else: print(f"      [警告] 現在ウィンドウ({current_handle[-6:]})がメインウィンドウ({main_window[-6:]})と同じため閉じません。")
                                    driver.switch_to.window(main_window); time.sleep(0.3)
                                    if syllabus_details: scraped_data_all_years.append(syllabus_details); opened_links_this_year_field.add(syllabus_url); processed_count_on_page += 1
                                    else: print(f"      [警告] 詳細情報取得失敗(None)。スキップ。 URL: {syllabus_url}"); save_screenshot(driver, f"detail_processing_failed_{year}_p{current_page}", screenshots_dir)

                                # --- ★★★ MissingCriticalDataError 捕捉とスクリプト終了 ★★★ ---
                                except MissingCriticalDataError as e_critical:
                                    print(f"\n[!!!] 必須データ欠落のため処理を緊急停止します: {e_critical}")
                                    save_screenshot(driver, "critical_data_missing", screenshots_dir)
                                    sys.exit(1) # ★ スクリプトを終了コード1で停止

                                except TimeoutException as e_tab: print(f"      [警告] 新タブ処理タイムアウト: {e_tab}。スキップ。"); save_screenshot(driver, f"tab_open_timeout_{year}_p{current_page}", screenshots_dir); current_windows=driver.window_handles; # (タブクローズ処理省略)
                                except NoSuchWindowException as e_win: print(f"      [エラー] ウィンドウ消失: {e_win}。年度中断。"); year_processed_successfully = False; raise
                                except (InvalidSessionIdException) as e_session: print(f"      [エラー] セッションエラー: {e_session}。年度中断。"); year_processed_successfully = False; raise
                                except Exception as e_detail: print(f"      [エラー] 個別シラバス処理エラー: {e_detail}"); save_screenshot(driver, f"detail_unknown_error_{year}_p{current_page}", screenshots_dir); traceback.print_exc(); # (ウィンドウ回復処理省略)

                            if not year_processed_successfully: break # URLループ中に中断フラグが立ったら抜ける
                            # print(f"    ページ {current_page} で {processed_count_on_page} 件の新規シラバスを処理しました。") # Log suppressed

                            # --- 次ページへ ---
                            try:
                                next_xpath = "//li[not(contains(@class, 'disabled'))]/a[contains(text(), '次') or contains(., 'Next')]"
                                next_button = WebDriverWait(driver, MEDIUM_WAIT).until(EC.element_to_be_clickable((By.XPATH, next_xpath)))
                                if click_element(driver, next_button): current_page += 1; WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath))); time.sleep(SHORT_WAIT)
                                else: print("    [警告] 次ページクリック失敗。ページネーション終了。"); save_screenshot(driver, f"next_page_click_failed_p{current_page}_{year}", screenshots_dir); break
                            except TimeoutException: print(f"    次ページボタンなし。最終ページ。"); break
                            except StaleElementReferenceException: print("    [警告] 次ページボタンStale。ページネーション終了。"); save_screenshot(driver, f"next_page_stale_p{current_page}_{year}", screenshots_dir); break
                            except Exception as e_page: print(f"   [エラー] ページネーションエラー: {e_page}"); save_screenshot(driver, f"pagination_error_p{current_page}_{year}", screenshots_dir); break

                        # --- 年度ループ内 try 終了 ---
                        if year_processed_successfully: year_processed_successfully = True; year_index += 1
                        else: raise Exception("年度処理中断") # 上位のexceptで捕捉 -> WebDriver再起動

                    except (InvalidSessionIdException, NoSuchWindowException) as e_session_year:
                        print(f"\n[!!!] 年度 {year} セッション/ウィンドウエラー: {e_session_year}。WebDriver再起動試行。")
                        save_screenshot(driver, f"year_session_error_{year}", screenshots_dir)
                        if driver: try: driver.quit() except: pass
                        driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                        if not driver: raise Exception("WebDriver再初期化失敗。")
                        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir): raise Exception("再ログイン失敗。")
                        print(f"      WebDriver再起動完了。年度 {year} を再試行。"); continue
                    except Exception as e_year_main:
                        print(f"  [エラー] {year}年度処理中の予期せぬエラー: {e_year_main}"); save_screenshot(driver, f"year_main_unknown_error_{year}", screenshots_dir); traceback.print_exc(); print("      年度スキップ。"); year_index += 1
                    # finally: print(f"--- {year}年度の処理終了 ---") # Log suppressed

                # --- 分野ループ内 try 終了 ---
                field_processed_successfully = True; field_index += 1

            except (InvalidSessionIdException, NoSuchWindowException) as e_session_field:
                print(f"\n[!!!] 分野 '{field_name}' セッション/ウィンドウエラー: {e_session_field}。WebDriver再起動試行。")
                save_screenshot(driver, f"field_session_error_{field_name}", screenshots_dir)
                if driver: try: driver.quit() except: pass
                driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                if not driver: raise Exception("WebDriver再初期化失敗。")
                if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir): raise Exception("再ログイン失敗。")
                print(f"      WebDriver再起動完了。分野 '{field_name}' を再試行。"); continue
            except Exception as e_field_main:
                print(f"  [エラー] 分野 '{field_name}' 処理中の予期せぬエラー: {e_field_main}"); save_screenshot(driver, f"field_main_unknown_error_{field_name}", screenshots_dir); traceback.print_exc(); print("      分野スキップ。"); field_index += 1
            # finally: print(f"===== 分野: {field_name} の処理終了 =====") # Log suppressed

    # --- グローバル try ブロック終了 ---
    except KeyboardInterrupt: print("\nキーボード割り込み。処理中断...")
    except SystemExit as e: print(f"\nスクリプトが意図的に停止されました (終了コード: {e.code})。") # sys.exit()を捕捉
    except Exception as e_global: print(f"\n★★★ 予期せぬ重大エラー: {e_global} ★★★"); traceback.print_exc(); save_screenshot(driver, "fatal_error", screenshots_dir)
    finally:
        if driver: try: driver.quit(); print("\nブラウザを閉じました。") except Exception as qe: print(f"\nブラウザ終了時エラー: {qe}")
        print("\n=== 最終処理 ===")
        if scraped_data_all_years:
            print(f"合計 {len(scraped_data_all_years)} 件の生データを取得しました。")
            print("\nデータを集約しています...")
            final_json_data = aggregate_syllabus_data(scraped_data_all_years)
            if final_json_data:
                print(f"集約後のデータ件数: {len(final_json_data)}")
                print(f"\n最終データを '{output_json_path}' に書き込んでいます...")
                try:
                    with open(output_json_path, mode='w', encoding='utf-8') as f: json.dump(final_json_data, f, ensure_ascii=False, indent=4)
                    print(f"JSONファイル書き込み完了。")
                except Exception as e: print(f"[エラー] JSONファイル書き込みエラー: {e}")
            else: print("集約後データなし。JSONファイル未作成。")
        else: print("\n有効データなし。")
        end_time = time.time(); elapsed_time = end_time - global_start_time
        print(f"\n処理時間: {elapsed_time:.2f} 秒"); print(f"スクレイピング終了: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")