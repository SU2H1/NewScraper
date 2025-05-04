# -*- coding: utf-8 -*-
# --- ライブラリインポート ---
#Windows Virtual Environment Activation: .\.venv\Scripts\activate.ps1
#Mac Virtual Environment Activation: source .venv/bin/activate
from threading import Lock  # <-- ADD THIS
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
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import random
import pickle
import datetime
# pprint をインポートしてターミナル出力を整形 (オプション)
# from pprint import pprint
# ★★★ 並列処理ライブラリは削除 ★★★
#from concurrent.futures import ThreadPoolExecutor
#import concurrent.futures


# --- グローバル変数・設定 ---
CHROME_DRIVER_PATH = None # ChromeDriverのパス (Noneの場合は自動検出)
OPENED_LINKS_LOCK = Lock()  # <-- ADD THIS
USER_EMAIL = 'Username' # ログインに使用するメールアドレス
USER_PASSWORD = 'Password' # ログインに使用するパスワード
OUTPUT_DIR_NAME = 'syllabus_output' # 出力ディレクトリ名
OUTPUT_JSON_FILE = 'syllabus_data.json' # 出力JSONファイル名
TARGET_FIELDS = ["特設科目"] # スクレイピング対象の分野
#TARGET_FIELDS = ["基盤科目", "先端科目", "特設科目"] # スクレイピング対象の分野
TARGET_YEARS = [2024] # スクレイピング対象の年度
#TARGET_YEARS = [2025, 2024, 2023] # スクレイピング対象の年度
CONSECUTIVE_ERROR_THRESHOLD = 10  # 連続エラーの最大許容数 (値を増加)
ERROR_RATE_THRESHOLD = 0.8  # エラー率の許容閾値（80%に増加）
MIN_SAMPLES_BEFORE_CHECK = 20  # エラー率チェック前の最小サンプル数 (増加)
ENABLE_AUTO_HALT = True  # 自動停止機能の有効/無効
# ★★★ ヘッドレスモードを有効化して高速化 ★★★
HEADLESS_MODE = False # Trueにするとヘッドレスモードで実行
PAGE_LOAD_TIMEOUT = 60 # タイムアウト時間半減 (60→30秒)
ELEMENT_WAIT_TIMEOUT = 90 # 要素待機時間半減 (90→45秒)
# ★★★ 待機時間を大幅短縮 ★★★
SHORT_WAIT = 0.4 # 短い待機時間を短縮 (1.0→0.3秒)
MEDIUM_WAIT = 1.0 # 中程度の待機時間を短縮 (1.3→0.5秒)
LONG_WAIT = 2.0 # 長い待機時間を短縮 (1.5→0.7秒)
# ★★★ 英語ページでのJSレンダリング待機時間短縮 ★★★
JS_RENDER_WAIT = 0.4 # 秒 (大幅短縮 1.0→0.3秒)

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
    'location': ("教室", "//tr[th[contains(text(),'教室') or contains(text(),'開講場所')]]/td", "教室不明"),
    'day_period': ("曜日時限", "//tr[th[contains(text(),'曜日時限')]]/td", "曜日時限不明"), # 曜日時限のXPath
    'selection_method': ("選抜方法", "//tr[th[contains(text(),'選抜方法')]]/td", ""), # 選抜方法のXPath
    'class_format': ("授業実施形態", "//tr[th[contains(text(),'授業実施形態')]]/td", ""),
    'course_id_fallback': ("登録番号(表)", "//tr[th[normalize-space()='登録番号']]/td", None)
}

INFO_MAP_JA_2023_2024 = {
    'name': ("科目名", "//h2/span[@class='title']", "名称不明"),
    'semester': ("学期", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='開講年度・学期']/following-sibling::dd[1]", "学期不明"),
    'professor': ("担当者名", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='授業教員名']/following-sibling::dd[1]", ""),
    'credits': ("単位", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='単位']/following-sibling::dd[1]", "単位不明"),
    'field': ("分野", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='分野']/following-sibling::dd[1]", "分野不明"),
    'location': ("教室", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='開講場所']/following-sibling::dd[1]", "教室不明"),
    'day_period': ("曜日時限", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='曜日・時限']/following-sibling::dd[1]", "曜日時限不明"),
    'selection_method': ("選抜方法", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='選抜方法']/following-sibling::dd[1]", ""),
    'class_format': ("授業実施形態", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='実施形態']/following-sibling::dd[1]", ""),
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
    'selection_method': ("Selection Method", "//tr[th[normalize-space()='Selection Method']]/td", ""), # Changed from 'Lottery Method'
    'class_format': ("Class Format", "//tr[th[normalize-space()='Class Format']]/td", ""),
    'course_id_fallback': ("Registration Number", "//tr[th[normalize-space()='Registration Number']]/td", None)
}

INFO_MAP_EN_2023_2024 = {
    'name': ("Course Title", "//h2/span[@class='title']", "Name Unknown"),
    'semester': ("Year/Semester", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Year/Semester']/following-sibling::dd[1]", "Semester Unknown"),
    'professor': ("Lecturer(s)", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Lecturer Name']/following-sibling::dd[1]", ""),
    'credits': ("Credits", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Unit']/following-sibling::dd[1]", "Credits Unknown"),
    'field': ("Field", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Field']/following-sibling::dd[1]", "Field Unknown"),
    'location': ("Classroom", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Location']/following-sibling::dd[1]", "Classroom Unknown"),
    'day_period': ("Day/Period", "//div[contains(@class,'syllabus-info')]//dl/dt[normalize-space()='Day of Week・Period']/following-sibling::dd[1]", "Day/Period Unknown"),
    'selection_method': ("Selection Method", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Selection Method']/following-sibling::dd[1]", ""),
    'class_format': ("Class Format", "//div[contains(@class,'syllabus-info')]//dl/dt[contains(text(),'Class Format')]/following-sibling::dd[1]", ""),
    'course_id_fallback': ("Registration Number", "//div[contains(@class,'subject')]//dl/dt[normalize-space()='Course Registration Number']/following-sibling::dd[1]", None)
}


# --- ヘルパー関数 ---

def load_credentials():
    try:
        # Store this file outside the code directory or add to .gitignore
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get('username'), config.get('password')
    except Exception as e:
        print(f"Error loading credentials: {e}")
        return None, None

USER_EMAIL, USER_PASSWORD = load_credentials()

if not USER_EMAIL or not USER_PASSWORD:
    print("Error: Couldn't load credentials from config.json")
    sys.exit(1)


def create_output_dirs(base_dir=OUTPUT_DIR_NAME):
    """出力ディレクトリを作成する"""
    logs_dir = os.path.join(base_dir, "logs")
    screenshots_dir = os.path.join(base_dir, "screenshots")
    for dir_path in [base_dir, logs_dir, screenshots_dir]:
        os.makedirs(dir_path, exist_ok=True)
    return base_dir, logs_dir, screenshots_dir

# 高速化版関数群

def save_screenshot(driver, prefix="screenshot", dir_path="screenshots"):
    """スクリーンショットを保存する - 重要なエラーのみ"""
    # 重要なエラーのみスクリーンショット
    if "critical" not in prefix and "error" not in prefix:
        return None  # Skip non-critical screenshots
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(dir_path, filename)
        driver.save_screenshot(filepath)
        return filepath
    except:
        return None

def get_text_by_xpath(driver, xpath, default=""):
    """Get text from element using standard Selenium methods instead of JavaScript"""
    if not xpath:
        return default
    try:
        # Simple, reliable approach
        element = WebDriverWait(driver, SHORT_WAIT).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        text = element.text
        return normalize_text(text) if text else default
    except Exception:
        return default

def get_multiple_elements_text(driver, xpaths_dict):
    """Multiple XPaths to text values in a single JS call"""
    js_script = """
        function getTexts(xpaths) {
            var results = {};
            for (var key in xpaths) {
                try {
                    var element = document.evaluate(xpaths[key], document, null, 
                                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    results[key] = element ? element.textContent.trim() : "";
                } catch(e) {
                    results[key] = "";
                }
            }
            return results;
        }
        return getTexts(arguments[0]);
    """
    try:
        # Create dictionary of only xpath values
        xpath_values = {k: v[1] for k, v in xpaths_dict.items() if k != 'course_id_fallback'}
        results = driver.execute_script(js_script, xpath_values)
        
        # Apply normalization
        for key in results:
            results[key] = normalize_text(results[key])
            
        return results
    except:
        # Fallback to traditional method
        return {k: get_text_by_xpath(driver, v[1], v[2]) 
                for k, v in xpaths_dict.items() if k != 'course_id_fallback'}


def process_single_url(syllabus_url, year, screenshots_dir, opened_links_this_year_field, auth_cookies=None):
    """Process a single syllabus URL with session recovery capabilities"""
    url_start_time = time.time()
    course_id = "unknown"
    original_url = None  # Initialize outside try-block to avoid scope issues
    max_retries = 2  # Add retry limit
    
    for attempt in range(max_retries):
        try:
            driver = globals()['driver']
            # Store original URL FIRST before any operations that might fail
            original_url = driver.current_url
            
            print(f"\n[{time.strftime('%H:%M:%S')}] 🔍 Processing URL: {syllabus_url}")
            
            # Direct navigation instead of tab-based approach
            driver.get(syllabus_url)
            
            # Wait for page to load properly
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(MEDIUM_WAIT)
            
            # Process the syllabus details
            print(f"[{time.strftime('%H:%M:%S')}] 📊 Extracting syllabus details")
            details = get_syllabus_details(driver, year, screenshots_dir)
            
            # Extract identifying information for logging
            if details:
                course_id = details.get('course_id', 'unknown')
                course_name = details.get('translations', {}).get('ja', {}).get('name', 'Unknown')
                professor = details.get('professor_ja', 'Unknown')
                field = details.get('field_ja', 'Unknown')
            
            # Return to search results page
            print(f"[{time.strftime('%H:%M:%S')}] 🔙 Returning to search results page")
            driver.get(original_url)
            time.sleep(SHORT_WAIT)
            
            # Calculate elapsed time
            elapsed_time = time.time() - url_start_time
            
            # Log the result
            if details:
                print(f"[{time.strftime('%H:%M:%S')}] ✅ SUCCESS ({elapsed_time:.2f}s): ID:{course_id} | {course_name} | Prof:{professor} | Field:{field}")
                return details
            else:
                print(f"[{time.strftime('%H:%M:%S')}] ❌ FAILED ({elapsed_time:.2f}s): {syllabus_url}")
                # If we've tried multiple times already, give up
                if attempt == max_retries - 1:
                    return None
                # Otherwise try again
                print(f"[{time.strftime('%H:%M:%S')}] 🔄 Retrying... (Attempt {attempt+2}/{max_retries})")
                time.sleep(MEDIUM_WAIT)
                
        except InvalidSessionIdException as e_session:
            elapsed_time = time.time() - url_start_time
            print(f"[{time.strftime('%H:%M:%S')}] 🔄 SESSION ERROR ({elapsed_time:.2f}s): {str(e_session)} | URL: {syllabus_url}")
            
            # Try to recover the WebDriver session
            if recover_driver_session():
                # If recovery succeeded and this wasn't our last attempt, retry
                if attempt < max_retries - 1:
                    print(f"[{time.strftime('%H:%M:%S')}] 🔄 Session recovered, retrying... (Attempt {attempt+2}/{max_retries})")
                    try:
                        # Navigate back to search results
                        driver = globals()['driver']  # Get the new driver
                        driver.get('https://gslbs.keio.jp/syllabus/search')
                        time.sleep(MEDIUM_WAIT)
                        
                        # Re-execute the search with the same criteria
                        js_script = """
                            async function setSearchCriteria(year, fieldName) {
                                try {
                                    var yearSelect = document.querySelector('select[name="KEYWORD_TTBLYR"]');
                                    if (yearSelect) { 
                                        yearSelect.value = year; 
                                        yearSelect.dispatchEvent(new Event('change', {bubbles:true})); 
                                    }
                                    
                                    var toggleButton = document.querySelector('button[data-target*="screensearch-cond-option-toggle-target"]');
                                    if (toggleButton) {
                                        var toggleTarget = document.querySelector(toggleButton.getAttribute('data-target'));
                                        if (toggleTarget && !toggleTarget.classList.contains('show')) {
                                            toggleButton.click(); 
                                            await new Promise(r => setTimeout(r, 700));
                                        }
                                    }
                                    
                                    var fieldSelect = document.querySelector('select[name="KEYWORD_FLD1CD"]');
                                    if (fieldSelect) {
                                        for (let i = 0; i < fieldSelect.options.length; i++) {
                                            if (fieldSelect.options[i].text.trim() === fieldName) {
                                                fieldSelect.selectedIndex = i; 
                                                fieldSelect.dispatchEvent(new Event('change', {bubbles:true}));
                                                break;
                                            }
                                        }
                                    }
                                    
                                    // Click search button
                                    var searchBtn = document.querySelector('button[data-action_id="SYLLABUS_SEARCH_KEYWORD_EXECUTE"]');
                                    if (searchBtn) {
                                        searchBtn.click();
                                        return true;
                                    }
                                    return false;
                                } catch (error) { 
                                    return false; 
                                }
                            }
                            return await setSearchCriteria(arguments[0], arguments[1]);
                        """
                        driver.execute_script(js_script, str(year), "特設科目")
                        time.sleep(MEDIUM_WAIT * 2)  # Wait for search results
                        
                        # Continue to next attempt
                        continue
                    except Exception as e_recovery:
                        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Recovery navigation failed: {str(e_recovery)}")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ❌ Max retries reached for this URL")
            
            # If recovery failed or max retries reached, return None
            return None
            
        except Exception as e:
            # Calculate elapsed time for errors too
            elapsed_time = time.time() - url_start_time
            print(f"[{time.strftime('%H:%M:%S')}] ❌ ERROR ({elapsed_time:.2f}s): {str(e)} | URL: {syllabus_url}")
            
            # Try to recover by returning to the original page if possible
            if original_url:  # Only attempt if original_url was successfully captured
                try:
                    driver.get(original_url)
                    time.sleep(SHORT_WAIT)
                except Exception as e_recovery:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Recovery failed: {str(e_recovery)}")
            
            # If we've tried multiple times already, give up
            if attempt == max_retries - 1:
                return None
            # Otherwise try again after a short delay
            print(f"[{time.strftime('%H:%M:%S')}] 🔄 Retrying... (Attempt {attempt+2}/{max_retries})")
            time.sleep(MEDIUM_WAIT)
    
    # If we've gone through all retries and still failed
    return None

def select_option_by_text(driver, select_element, text):
    """セレクト要素から指定されたテキストのオプションを選択する (最適化版)"""
    try:
        # JavaScriptで直接選択 (高速化)
        js_script = """
            // 高速セレクション
            let found = false;
            let select = arguments[0];
            let targetText = arguments[1];
            
            // まず完全一致を試す（最速）
            for(let i = 0; i < select.options.length; i++) {
                if(select.options[i].text.trim() === targetText) {
                    select.selectedIndex = i;
                    select.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                }
            }
            
            // 部分一致を試す
            for(let i = 0; i < select.options.length; i++) {
                if(select.options[i].text.trim().includes(targetText)) {
                    select.selectedIndex = i;
                    select.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                }
            }
            
            return false;
        """
        result = driver.execute_script(js_script, select_element, text)
        if result:
            return True
            
        # JavaScriptで失敗した場合のみSeleniumを試す
        # 元のコードを残りとして使用
        
        return False
    except Exception:
        return False

def normalize_text(text):
    """テキストを正規化する (全角スペースを半角に、連続空白を1つに)"""
    if isinstance(text, str):
        text = text.replace('　', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    return ""

def normalize_field(field_text):
    """分野表記を正規化する"""
    if not field_text:
        return field_text
        
    # 先端科目環境情報系 → 先端科目-環境情報系
    if '先端科目' in field_text and '-' not in field_text:
        # Find where the prefix ends and add the hyphen
        for i in range(len('先端科目'), len(field_text)):
            if field_text[i] in '環先総政情経':  # Common first characters of field names
                return field_text[:i] + '-' + field_text[i:]
    return field_text

def normalize_credits(credits_text, language='en'):
    """単位表記を正規化する"""
    if not credits_text:
        return credits_text
        
    # Extract just the number using regex
    number_match = re.search(r'\d+', credits_text)
    if not number_match:
        return credits_text  # If no number found, return as-is
    
    number = number_match.group()
    
    # Format according to language
    if language == 'en':
        return f"{number} Credits"
    else:  # Japanese
        return f"{number}単位"

def parse_professor_names(ja_names_text, en_names_text=None):
    """教授名をセミコロンで区切って正しくパースし、日英の名前を対応付ける"""
    ja_names = []
    en_names = []
    
    # Parse Japanese names
    if ja_names_text:
        if ';' in ja_names_text:
            ja_names = [name.strip() for name in ja_names_text.split(';') if name.strip()]
        else:
            ja_names = [name.strip() for name in ja_names_text.split(',') if name.strip()]
            # If there's only one entry but it has a space (like "一ノ瀬 友博"), treat it as one name
            if len(ja_names) == 1 and ' ' in ja_names[0]:
                ja_names = [ja_names[0]]
    
    # Parse English names
    if en_names_text:
        if ';' in en_names_text:
            en_names = [name.strip() for name in en_names_text.split(';') if name.strip()]
        else:
            # For English names with format "LASTNAME, FIRSTNAME"
            # we need special handling to avoid splitting a single name
            if ',' in en_names_text and ';' not in en_names_text:
                # Try to detect if this is multiple professors or just one with lastname, firstname format
                comma_parts = en_names_text.split(',')
                if len(comma_parts) == 2 and not any(p.strip().isupper() for p in comma_parts):
                    # Likely a single name in "Lastname, Firstname" format
                    en_names = [en_names_text.strip()]
                else:
                    # Multiple names separated by commas
                    en_names = [name.strip() for name in comma_parts if name.strip()]
            else:
                en_names = [en_names_text.strip()]
    
    # Match names or use defaults
    num_ja_names = len(ja_names)
    num_en_names = len(en_names)
    
    # Create pairs of names
    professors = []
    for i in range(max(num_ja_names, num_en_names)):
        ja_name = ja_names[i] if i < num_ja_names else ""
        en_name = en_names[i] if i < num_en_names else ja_name
        
        professors.append({
            "ja": ja_name,
            "en": en_name
        })
    
    return professors
    return professors

def click_element(driver, element, wait_time=SHORT_WAIT):
    """Click an element with safer approach"""
    try:
        WebDriverWait(driver, wait_time).until(EC.element_to_be_clickable(element))
        element.click()
        time.sleep(SHORT_WAIT)  # Give time for the click to register
        return True
    except Exception:
        try:
            # Only use JavaScript click as fallback
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(SHORT_WAIT)
            driver.execute_script("arguments[0].click();", element)
            time.sleep(SHORT_WAIT)
            return True
        except Exception:
            return False


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

def display_scraped_info(syllabus_details, title="Scraped Syllabus Information"):
    """Display scraped syllabus information in a readable format for visual verification"""
    if not syllabus_details:
        print("\n=== No syllabus details found ===\n")
        return
        
    print(f"\n{'='*60}")
    print(f"=== {title} ===")
    print(f"{'='*60}")
    
    print(f"Course ID: {syllabus_details.get('course_id', 'N/A')}")
    print(f"Year: {syllabus_details.get('year_scraped', 'N/A')}")
    print(f"Semester: {syllabus_details.get('semester', 'N/A')}")
    
    # Display Japanese data
    print("\n--- JAPANESE DATA ---")
    ja_data = syllabus_details.get('translations', {}).get('ja', {})
    for key, value in ja_data.items():
        print(f"{key}: {value}")
    
    # Display English data
    print("\n--- ENGLISH DATA ---")
    en_data = syllabus_details.get('translations', {}).get('en', {})
    for key, value in en_data.items():
        print(f"{key}: {value}")
    
    # Display other important fields
    print(f"\nProfessor (JA): {syllabus_details.get('professor_ja', 'N/A')}")
    print(f"Name (JA): {syllabus_details.get('name_ja', 'N/A')}")
    print(f"Field (JA): {syllabus_details.get('field_ja', 'N/A')}")
    print(f"Credits (JA): {syllabus_details.get('credits_ja', 'N/A')}")
    
    print(f"{'='*60}\n")

def is_error_page(driver):
    """
    検出したページがエラーページかどうかを確認する
    """
    try:
        # タイトルチェック
        page_title = driver.title
        if "Error" in page_title or "404" in page_title:
            print("           [情報] エラーページのタイトルを検出しました。スキップします。")
            return True
            
        # エラーメッセージの検出
        error_messages = [
            "//h1[contains(text(), 'Error')]",
            "//p[contains(text(), 'ページが見つかりません')]",
            "//p[contains(text(), 'Page Not Found')]",
            "//div[contains(text(), 'ページが見つかりません')]",
            "//div[contains(text(), 'Page Not Found')]"
        ]
        
        for xpath in error_messages:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                if elements and any(element.is_displayed() for element in elements):
                    print(f"           [情報] エラーページのメッセージを検出しました: {xpath}")
                    return True
            except Exception:
                continue
                
        # URLチェック
        current_url = driver.current_url
        if "error" in current_url.lower() or "appMsg" in current_url:
            print(f"           [情報] エラーページのURLパターンを検出: {current_url}")
            return True
            
        return False
    except Exception as e:
        print(f"           [警告] エラーページチェック中に例外が発生: {e}")
        return False

# スクリプト内で特定のURLをテストする場合に追加できるデバッグコード

def test_error_page_detection(driver, test_url):
    """
    エラーページ検出機能をテストする関数
    """
    print(f"\n=== エラーページ検出テスト開始: {test_url} ===")
    try:
        # URLに移動
        driver.get(test_url)
        WebDriverWait(driver, min(30, ELEMENT_WAIT_TIMEOUT)).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        # time.sleep削除 - 即時処理に変更
        
        # ページ情報出力
        print(f"ページタイトル: {driver.title}")
        print(f"URL: {driver.current_url}")
        
        # エラーページ検出テスト
        is_error = is_error_page(driver)
        print(f"エラーページ判定結果: {'エラーページです' if is_error else 'エラーページではありません'}")
        
        # ページのHTML構造をデバッグ出力
        try:
            h1_elements = driver.find_elements(By.TAG_NAME, "h1")
            print(f"H1要素数: {len(h1_elements)}")
            for i, el in enumerate(h1_elements):
                print(f"  H1 #{i+1}: {el.text}")
            
            p_elements = driver.find_elements(By.TAG_NAME, "p")
            print(f"p要素数: {len(p_elements)}")
            for i, el in enumerate(p_elements[:5]):  # 最初の5つだけ表示
                print(f"  p #{i+1}: {el.text}")
            
            # エラーメッセージに関連する要素を特定
            print("\nエラーメッセージ関連要素:")
            error_selectors = [
                "//h1[contains(text(), 'Error')]",
                "//p[contains(text(), 'ページが見つかりません')]",
                "//p[contains(text(), 'Page Not Found')]",
                "//div[contains(text(), 'ページが見つかりません')]",
                "//div[contains(text(), 'Page Not Found')]"
            ]
            
            for selector in error_selectors:
                elements = driver.find_elements(By.XPATH, selector)
                if elements:
                    print(f"  {selector}: {len(elements)}個の要素を検出")
                    for i, el in enumerate(elements):
                        print(f"    要素 #{i+1}: {el.text}, 表示状態: {el.is_displayed()}")
                else:
                    print(f"  {selector}: 該当要素なし")
            
        except Exception as e:
            print(f"HTML構造出力中にエラー: {e}")
        
    except Exception as e:
        print(f"テスト実行中にエラー: {e}")
        traceback.print_exc()
    
    print("=== エラーページ検出テスト終了 ===\n")
    return

# テスト実行例
# test_error_page_detection(driver, "https://syllabus.sfc.keio.ac.jp/error")

def save_checkpoint(year, field_name, page_num, processed_urls):
    """進捗状況をチェックポイントファイルに保存する"""
    checkpoint = {
        'year': year,
        'field_name': field_name,
        'page_num': page_num,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'processed_urls': list(processed_urls)  # setをリストに変換
    }
    
    checkpoint_file = os.path.join(OUTPUT_DIR_NAME, 'checkpoint.pkl')
    with open(checkpoint_file, 'wb') as f:
        pickle.dump(checkpoint, f)
    print(f"\n[情報] チェックポイント保存: 年度={year}, 分野={field_name}, ページ={page_num}, URL数={len(processed_urls)}")

def load_checkpoint():
    """最後のチェックポイントを読み込む（存在する場合）"""
    checkpoint_file = os.path.join(OUTPUT_DIR_NAME, 'checkpoint.pkl')
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'rb') as f:
                checkpoint = pickle.load(f)
            print(f"\n[情報] チェックポイント読込: 年度={checkpoint['year']}, 分野={checkpoint['field_name']}, "
                  f"ページ={checkpoint['page_num']}, 保存日時={checkpoint['timestamp']}")
            return checkpoint
        except Exception as e:
            print(f"\n[警告] チェックポイント読込失敗: {e}")
    return None

def get_syllabus_details(driver, current_year, screenshots_dir):
    """
    シラバス詳細ページから指定された日本語と英語の情報を取得。
    日本語ページと英語ページを個別に処理し、それぞれの言語の情報を格納する。
    年度とシステムタイプに応じて適切なXPathマップを使用する。
    """
    # Add timer for detailed logging
    detail_start_time = time.time()
    
    ja_data = {}  # 日本語ページから取得したデータ
    en_data = {}  # 英語ページから取得したデータ
    course_id = None
    japanese_url = "N/A"
    english_url = "N/A"  # 英語URLも初期化

    # システムタイプを判定
    current_url = driver.current_url
    is_old_system = "syllabus.sfc.keio.ac.jp" in current_url
    is_new_system = "gslbs.keio.jp" in current_url
    
    if is_old_system or (current_year <= 2024 and not is_new_system):
        print(f"    [{time.strftime('%H:%M:%S')}] 📋 Processing old system syllabus (pre-2024)")
        # 旧システム用のXPath定義（SFC 2024年対応版）
        ja_map_to_use = INFO_MAP_JA_2023_2024.copy()  # Use the 2023/2024 mapping
        en_map_to_use = INFO_MAP_EN_2023_2024.copy()  # Use the 2023/2024 mapping
    else:
        print(f"    [{time.strftime('%H:%M:%S')}] 📋 Processing new system syllabus (2025+)")
        # 新システム用のXPath定義（2025年以降用）
        ja_map_to_use = INFO_MAP_JA_2025.copy()
        en_map_to_use = INFO_MAP_EN_2025.copy()

    # --- Course ID 取得 ---
    print(f"    [{time.strftime('%H:%M:%S')}] 🔢 Extracting course ID")
    try:
        # 旧システムと新システムで異なるパターンを使用
        if is_old_system or current_year <= 2024:
            # 旧システム用のコースID取得パターン
            id_match = re.search(r'/courses/\d+_(\d+)', current_url) or \
                    re.search(r'\?id=(\d+)', current_url)
        else:
            # 新システム用のコースID取得パターン - 2025 format
            id_match = re.search(r'[?&](?:id|entno)=(\d+)', current_url) or \
                    re.search(r'/courses/\d+_(\d+)', current_url) or \
                    re.search(r'/syllabus/(\d+)', current_url) or \
                    re.search(r'ttblyr=\d+&entno=(\d+)', current_url) 
            
        if id_match:
            course_id = id_match.group(1)
        else:
            course_id_xpath = ja_map_to_use.get('course_id_fallback', [None, None])[1]
            if course_id_xpath:
                print(f"               URLからID取得失敗。XPathで試行: {course_id_xpath}")
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
                                print(f"               隠し要素からID取得: {value}")
                                break
                    except Exception: pass
    except Exception as e:
        print(f"    [{time.strftime('%H:%M:%S')}] ⚠️ Error during Course ID extraction: {e}")

    if course_id:
        print(f"    [{time.strftime('%H:%M:%S')}] ✅ Course ID found: {course_id}")
    else:
        print(f"    [{time.strftime('%H:%M:%S')}] ⚠️ Failed to find Course ID, trying alternative methods")

    if not course_id:
        print(f"    [{time.strftime('%H:%M:%S')}] ❌ Critical: Failed to find Course ID")
        raise MissingCriticalDataError(f"必須データ(Course ID)の取得に失敗 (URL: {japanese_url})")
    print(f"               Course ID: {course_id}")

    # --- 日本語情報取得ループ ---
    print(f"    [{time.strftime('%H:%M:%S')}] 📝 Extracting Japanese syllabus data")
    name_default_ja = f"名称不明-{course_id}"
    name_tuple_ja = ja_map_to_use['name']
    ja_map_to_use['name'] = (name_tuple_ja[0], name_tuple_ja[1], name_default_ja)

    INVALID_COURSE_NAME_PATTERNS = ["慶應義塾大学 シラバス・時間割", "SFC Course Syllabus"]
    critical_data_missing_ja = False  # 日本語データ用のフラグ
    missing_details_ja = []  # 日本語データ用のリスト

    print("           --- 日本語情報取得開始 ---")
    for key, (label, xpath, default_value, *_) in ja_map_to_use.items():
        if key == 'course_id_fallback': continue
        ja_data[key] = get_text_by_xpath(driver, xpath, default_value)

        # 必須チェック (TTCK/Online処理前)
        optional_keys = ['professor', 'selection_method', 'class_format', 'location', 'day_period'] 
        if key not in optional_keys:
            if key == 'name':
                if ja_data[key] == default_value or any(pattern in ja_data[key] for pattern in INVALID_COURSE_NAME_PATTERNS):
                    critical_data_missing_ja = True
                    missing_details_ja.append(f"{label}(ja): 不適切「{ja_data[key]}」")
            elif ja_data[key] == default_value or not ja_data[key]:
                if xpath:  # XPathが定義されている場合のみエラー対象
                    critical_data_missing_ja = True
                    missing_details_ja.append(f"{label}(ja): 未取得/空")

        # --- Online/TTCK処理 (日本語) ---
        is_ttck_ja = "TTCK" in ja_data.get('name', '')
        is_online_ja = "オンライン" in ja_data.get('class_format', '') or "オンデマンド" in ja_data.get('class_format', '')

        if is_ttck_ja:
            print("               日本語: TTCKコース検出。教室と曜日時限を調整します。")
            ja_data['location'] = "TTCK"
            if not ja_data.get('day_period') or ja_data.get('day_period') == "曜日時限不明":
                ja_data['day_period'] = "特定期間集中"
        elif is_online_ja:
            print("               日本語: オンライン授業検出。教室と曜日時限を調整します。")
            ja_data['location'] = "オンライン"
            if not ja_data.get('day_period') or ja_data.get('day_period') == "曜日時限不明":
                ja_data['day_period'] = "オンライン授業"

        # --- 必須データ最終チェック (日本語) ---
        if not is_ttck_ja:
            if not ja_data.get('location') or ja_data.get('location') == "教室不明":
                 if not is_online_ja:
                    critical_data_missing_ja = True
                    missing_details_ja.append("教室(ja): 未取得/空")
            if not ja_data.get('day_period') or ja_data.get('day_period') == "曜日時限不明":
                critical_data_missing_ja = True
                missing_details_ja.append("曜日時限(ja): 未取得/空")

        if critical_data_missing_ja:
            raise MissingCriticalDataError(f"必須日本語データ取得失敗 (URL: {japanese_url}): {'; '.join(missing_details_ja)}")

        print("           --- 日本語情報取得完了 ---")

        # After Japanese extraction
        ja_elapsed = time.time() - detail_start_time
        print(f"    [{time.strftime('%H:%M:%S')}] ✅ Japanese data extracted ({ja_elapsed:.2f}s)")
        
        # --- 2. 英語ページの情報を取得 ---
        # English page processing
        english_start_time = time.time()
        print(f"    [{time.strftime('%H:%M:%S')}] 🇬🇧 Processing English page")

        # Generate English URL
        if is_old_system or current_year <= 2024:
            # Old system URL generation (unchanged)
            if "locale=ja" in current_url:
                english_url = current_url.replace("locale=ja", "locale=en")
            elif "locale=" not in current_url:
                english_url = current_url + ("&" if "?" in current_url else "?") + "locale=en"
            else:
                english_url = current_url
        else:
            # New system URL generation (2025+)
            if "lang=jp" in current_url:
                english_url = current_url.replace("lang=jp", "lang=en")
            elif "lang=" not in current_url:
                english_url = current_url + ("&" if "?" in current_url else "?") + "lang=en"
            else:
                english_url = current_url

        print(f"           英語ページ処理中: {english_url}")
        try:
            print(f"           英語ページに切り替え中...")
            # Use JavaScript to switch to English page
            js_switch_to_en = """
                // Optimized language switching function
                function switchToEnglish() {
                    // Find language button
                    const langBtn = document.querySelector('a[hreflang="en"], a.lang-en, a[onclick*="lang=en"]');
                    if (langBtn) {
                        langBtn.click();
                        return true;
                    } else {
                        // No button found, try URL modification instead
                        const url = new URL(window.location.href);
                        url.searchParams.set('lang', 'en');
                        window.location.href = url.toString();
                        return false;
                    }
                }
                return switchToEnglish();
            """
            used_button = driver.execute_script(js_switch_to_en)
            
            # Wait for page to be ready using conditional waiting instead of fixed sleep
            if used_button:
                # For button click, wait for a visual change indicating English is loaded
                # Note: No sleep needed, wait for a specific English indicator instead
                try:
                    WebDriverWait(driver, SHORT_WAIT).until(
                        EC.presence_of_element_located((By.XPATH, "//h2[@class='class-name']"))
                    )
                except TimeoutException:
                    # If timeout, the element might already be present or have a different structure
                    pass
            else:
                # For URL navigation, we need to wait for body to load
                WebDriverWait(driver, min(10, ELEMENT_WAIT_TIMEOUT)).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            
            # Check if this is an error page
            if is_error_page(driver):
                print(f"           [情報] 英語ページでエラーページを検出しました。英語情報は一部欠落します。")
                save_screenshot(driver, f"error_page_english_{current_year}_{course_id}", screenshots_dir)
                print("           英語ページはスキップして日本語情報のみで進めます。")
                # Set default English data
                en_data = {}
                name_default_en = f"Name Unknown-{course_id}"
                for key, (_, _, default_value_en, *_) in en_map_to_use.items():
                    en_data[key] = default_value_en if key != 'name' else name_default_en
            else:
                # No need for JS rendering wait - directly proceed to data extraction
                print(f"           英語ページ読み込み完了。情報取得試行...")
                print("           --- 英語情報取得開始 ---")
                
                # Batch retrieval of English data using JavaScript
                print("           英語情報を一括取得中...")
                en_data = {}
                name_default_en = f"Name Unknown-{course_id}"
                
                # Create dictionary of XPaths to query in a single JavaScript execution
                xpath_dict = {}
                for key, (label, xpath, default_value, *_) in en_map_to_use.items():
                    if key != 'course_id_fallback':
                        xpath_dict[key] = xpath
                
                # Optimized JavaScript for faster DOM queries 
                try:
                    js_script = """
                    function getElementTexts(xpathDict) {
                        const results = {};
                        // Process all XPaths in one pass
                        for (const [key, xpath] of Object.entries(xpathDict)) {
                            try {
                                // Fast DOM query using evaluate
                                const element = document.evaluate(
                                    xpath, 
                                    document, 
                                    null, 
                                    XPathResult.FIRST_ORDERED_NODE_TYPE, 
                                    null
                                ).singleNodeValue;
                                
                                // Store the text content if found, empty string if not
                                results[key] = element ? element.textContent.trim() : "";
                            } catch(e) {
                                results[key] = "";
                            }
                        }
                        return results;
                    }
                    return getElementTexts(arguments[0]);
                    """
                    
                    batch_results = driver.execute_script(js_script, xpath_dict)
                    
                    # Process results with normalization
                    for key, (_, _, default_value, *_) in en_map_to_use.items():
                        if key != 'course_id_fallback':
                            value = batch_results.get(key, "")
                            en_data[key] = normalize_text(value) if value else (default_value if key != 'name' else name_default_en)
                    
                    print("           英語情報の一括取得に成功しました。")
                except Exception as e:
                    print(f"           [警告] JavaScript一括取得中にエラー: {e}")
                    print("           従来の方法で個別に取得します...")
                    
                    # Fall back to original method
                    for key, (_, _, default_value_en, *_) in en_map_to_use.items():
                        en_data[key] = default_value_en if key != 'name' else name_default_en

                    for key, (label, xpath, default_value, *_) in en_map_to_use.items():
                        if key == 'course_id_fallback': continue
                        en_data[key] = get_text_by_xpath(driver, xpath, default_value)

                    for key, (label, xpath, default_value, *_) in en_map_to_use.items():
                        if key == 'course_id_fallback': continue
                        en_data[key] = get_text_by_xpath(driver, xpath, default_value)

                # --- Online/TTCK処理 (英語) ---
                is_ttck_en = ("TTCK" in en_data.get('name', '')) or is_ttck_ja
                en_class_format_lower = en_data.get('class_format', '').lower()
                is_online_en = "online" in en_class_format_lower or "remote" in en_class_format_lower

                if is_ttck_en:
                    print("               英語: TTCKコース検出。教室と曜日時限を調整します。")
                    en_data['location'] = "TTCK"
                    if not en_data.get('day_period') or en_data.get('day_period') == "Day/Period Unknown":
                        en_data['day_period'] = "Intensive Course"
                elif is_online_en:
                    print("               英語: オンライン授業検出。教室を調整します。")
                    en_data['location'] = "Online"

                print("           --- 英語情報取得完了 ---")

        except TimeoutException as e_timeout_en:
            print(f"     [警告] 英語ページ({english_url})の読み込みタイムアウト。英語情報は一部欠落します。 {e_timeout_en}")
            save_screenshot(driver, f"detail_en_load_timeout_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
            print(f"     [エラー] 英語ページ処理中にセッション/ウィンドウエラー: {e_session}")
            raise
        except Exception as e_en:
            print(f"     [警告] 英語ページ({english_url})の処理中に予期せぬエラー: {e_en}。英語情報は一部欠落します。")
            save_screenshot(driver, f"detail_en_unknown_error_{current_year}_{course_id or 'unknownID'}", screenshots_dir)
            traceback.print_exc()
            # エラー時は英語データをデフォルト値に戻す
            en_data = {}
            name_default_en = f"Name Unknown-{course_id}"
            for key, (_, _, default_value_en, *_) in en_map_to_use.items():
                en_data[key] = default_value_en if key != 'name' else name_default_en

        # After English extraction
        en_elapsed = time.time() - english_start_time
        print(f"    [{time.strftime('%H:%M:%S')}] ✅ English data extracted ({en_elapsed:.2f}s)")
        
        # Final data construction
        print(f"    [{time.strftime('%H:%M:%S')}] 🔄 Building final data object")
        
        # --- 3. 最終データ構築 ---
        final_details = {
            'course_id': course_id,
            'year_scraped': current_year,
            'translations': {
                'ja': {},
                'en': {}
            }
        }

        all_keys_to_copy = [k for k in ja_map_to_use.keys() if k != 'course_id_fallback']

        # 日本語データを構成
        for key in all_keys_to_copy:
            final_details['translations']['ja'][key] = ja_data.get(key, "")

        # 英語データを構成
        for key in all_keys_to_copy:
            final_details['translations']['en'][key] = en_data.get(key, "")

        # --- トップレベルの情報を設定 (補足用) ---
        semester_en_raw = final_details['translations']['en'].get('semester', '')
        semester_ja_raw = final_details['translations']['ja'].get('semester', '')
        final_details['semester'] = extract_season(semester_en_raw) if extract_season(semester_en_raw) != "unknown" else extract_season(semester_ja_raw)
        final_details['professor_ja'] = final_details['translations']['ja'].get('professor', '')
        final_details['name_ja'] = final_details['translations']['ja'].get('name', '')
        final_details['field_ja'] = final_details['translations']['ja'].get('field', '')
        final_details['credits_ja'] = final_details['translations']['ja'].get('credits', '')

        total_elapsed = time.time() - detail_start_time
        print(f"    [{time.strftime('%H:%M:%S')}] ✅ Complete syllabus details extracted ({total_elapsed:.2f}s)")
        
        # Display visual verification of scraped data
        display_scraped_info(final_details, f"Syllabus ID: {final_details.get('course_id', 'N/A')}")
        
        return final_details

# --- ★★★ aggregate_syllabus_data 関数 (変更なし) ★★★ ---
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
        course_id = item.get('course_id')
        professor_ja_key = item.get('professor_ja', '')
        professors_tuple = tuple(sorted([p.strip() for p in re.split('[/,]', professor_ja_key) if p.strip()]))
        name_ja_key = item.get('name_ja', '')
        semester_agg_key = item.get('semester', 'unknown')
        field_ja_key = item.get('field_ja', '')
        credits_ja_key = item.get('credits_ja', '')

        agg_key = (
            professors_tuple, name_ja_key, semester_agg_key, field_ja_key, credits_ja_key
        )

        if not name_ja_key or not field_ja_key or not credits_ja_key or semester_agg_key == "unknown":
            error_msg = f"集約キーに必要な情報が不足または学期不明 (Course ID: {course_id}, Year: {item.get('year_scraped')}, Semester: {semester_agg_key})"
            print(f"[警告] {error_msg}")
            
            if not pause_on_error(f"Missing critical aggregation data: {error_msg}"):
                print("ユーザーによる中断。スクリプトを終了します。")
                sys.exit(1)
            
            skipped_count += 1
            continue

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

        year_data_list.sort(key=lambda x: x['year_scraped'], reverse=True)
        latest_data = year_data_list[0]
        years_scraped_int = sorted(list(set(d['year_scraped'] for d in year_data_list)), reverse=True)
        available_years_str = [str(y) for y in years_scraped_int]

        trans_ja = latest_data.get('translations', {}).get('ja', {})
        trans_en = latest_data.get('translations', {}).get('en', {})
        semester_final = agg_key[2]

        professors_list = []
        prof_ja_raw = trans_ja.get('professor', '')
        prof_en_raw = trans_en.get('professor', '')

        # Use the new parsing function
        prof_ja_names = parse_professor_names(prof_ja_raw)
        prof_en_names = parse_professor_names(prof_en_raw)

        num_professors = len(prof_ja_names)
        if len(prof_en_names) < num_professors:
            prof_en_names.extend([""] * (num_professors - len(prof_en_names)))
        elif len(prof_en_names) > num_professors:
            prof_en_names = prof_en_names[:num_professors]

        # FIX: Set default empty values for department
        dept_ja = ""
        dept_en = ""

        for i in range(num_professors):
            prof_obj = {
                "name": {
                    "ja": prof_ja_names[i],
                    "en": prof_en_names[i] if i < len(prof_en_names) and prof_en_names[i] else prof_ja_names[i]
                },
                "department": { "ja": dept_ja, "en": dept_en }
            }
            professors_list.append(prof_obj)

        # Normalize field and credits
        field_ja = normalize_field(trans_ja.get('field', ''))
        field_en = normalize_field(trans_en.get('field', ''))
        credits_ja = normalize_credits(trans_ja.get('credits', ''), 'ja')
        credits_en = normalize_credits(trans_en.get('credits', ''), 'en')

        aggregated_item = {
            "course_id": latest_data['course_id'],
            "year": "&".join(available_years_str),
            "semester": semester_final,
            "translations": {
                "ja": {
                    "name": trans_ja.get('name', ''), 
                    "field": field_ja,
                    "credits": credits_ja, 
                    "semester": trans_ja.get('semester', ''),
                    "Classroom": trans_ja.get('location', ''), 
                    "day_period": trans_ja.get('day_period', ''),
                    "selection_method": trans_ja.get('selection_method', '')
                },
                "en": {
                    "name": trans_en.get('name', ''), 
                    "field": field_en,
                    "credits": credits_en, 
                    "semester": trans_en.get('semester', ''),
                    "Classroom": trans_en.get('location', ''), 
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
    login_url = 'https://gslbs.keio.jp/syllabus/search'
    max_login_attempts = 2
    for attempt in range(max_login_attempts):
        print(f"\nログイン試行 {attempt + 1}/{max_login_attempts}...")
        try:
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
                try:
                    print("     「次へ」ボタンが見つからないため、Enterキーを送信します。")
                    username_field.send_keys(Keys.RETURN)
                    time.sleep(MEDIUM_WAIT)
                except Exception as e_enter: print(f"     Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_next_button_error_{attempt+1}", screenshots_dir); raise Exception("「次へ」ボタン処理失敗")

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
                try:
                    print("     「サインイン」ボタンが見つからないため、Enterキーを送信します。")
                    password_field.send_keys(Keys.RETURN)
                    time.sleep(LONG_WAIT)
                except Exception as e_enter: print(f"     Enterキー送信中にエラー: {e_enter}"); save_screenshot(driver, f"login_signin_button_error_{attempt+1}", screenshots_dir); raise Exception("「サインイン」ボタン処理失敗")

            print("     ログイン後のページ遷移待機中...")
            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT + LONG_WAIT).until(EC.any_of(
                EC.url_contains("gslbs.keio.jp/syllabus/search"),
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '検索')] | //button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE']"))
            ))

            current_url = driver.current_url
            if "gslbs.keio.jp/syllabus/search" in current_url:
                print("ログイン成功、検索ページに到達しました。")
                try:
                    WebDriverWait(driver, MEDIUM_WAIT).until(EC.element_to_be_clickable((By.XPATH, "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(),'検索')]")))
                except TimeoutException:
                    print("[警告] 検索画面の主要要素確認タイムアウト。")
                return True
            else:
                print(f"[警告] ログイン後のURLが期待した検索ページではありません。 URL: {current_url}")
                save_screenshot(driver, f"login_unexpected_page_{attempt+1}", screenshots_dir)
                if "auth" in current_url or "verify" in current_url or "duo" in current_url or "device" in current_url:
                    print("[情報] 2段階認証またはデバイス確認ページに遷移した可能性があります。")
                    raise Exception("2段階認証/デバイス確認検出")
                print("     予期せぬページに遷移しました。ログイン失敗と判断します。")

        except (InvalidSessionIdException, NoSuchWindowException) as e_session:
            print(f"[エラー] ログイン処理中にセッション/ウィンドウエラー (試行 {attempt + 1}): {e_session}")
            raise
        except TimeoutException as e:
            print(f"[エラー] ログイン処理中にタイムアウト (試行 {attempt + 1})。")
            save_screenshot(driver, f"login_timeout_{attempt+1}", screenshots_dir)
            if attempt == max_login_attempts - 1: raise Exception("ログインタイムアウト") from e
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)
        except WebDriverException as e:
            print(f"[エラー] ログイン処理中にWebDriverエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_webdriver_error_{attempt+1}", screenshots_dir)
            if "net::ERR" in str(e) or "connection reset" in str(e).lower():
                print("     ネットワーク接続またはURLの問題、またはリモートホストによる切断の可能性があります。")
            if attempt == max_login_attempts - 1: raise Exception("ログイン中にWebDriverエラー") from e
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)
        except Exception as e:
            print(f"[エラー] ログイン処理中に予期せぬエラー (試行 {attempt + 1}): {e}")
            save_screenshot(driver, f"login_unknown_error_{attempt+1}", screenshots_dir)
            traceback.print_exc()
            if attempt == max_login_attempts - 1: raise Exception("ログイン中に予期せぬエラー") from e
            print("リトライします...")
            time.sleep(MEDIUM_WAIT)

    print("ログインに失敗しました。")
    return False

def extract_auth_cookies(driver):
    """ログイン済みのドライバーから認証Cookieを取得する"""
    try:
        return driver.get_cookies()
    except Exception as e:
        print(f"[エラー] Cookie取得中にエラー: {e}")
        return None

def apply_cookies(driver, cookies):
    """ドライバーにCookieを適用する"""
    if not cookies:
        return False
        
    try:
        # 対象ドメインに一度アクセスする必要がある
        driver.get("https://gslbs.keio.jp")
        
        # Cookieを適用
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"[警告] Cookie ({cookie.get('name', 'unknown')}) 適用エラー: {e}")
                
        # ページを更新してCookieを反映
        driver.refresh()
        return True
    except Exception as e:
        print(f"[エラー] Cookie適用中にエラーが発生しました: {e}")
        return False

# --- check_session_timeout 関数 (変更なし) ---
def check_session_timeout(driver, screenshots_dir):
    """セッションタイムアウトページが表示されているか確認する"""
    try:
        current_url = driver.current_url
        page_title = driver.title
        page_source = driver.page_source.lower()
        timeout_keywords = ["セッションタイムアウト", "session timeout", "ログインし直してください", "log back in"]
        error_page_url_part = "/syllabus/appMsg"
        is_session_timeout = False
        if error_page_url_part in current_url: is_session_timeout = True
        elif any(keyword in page_source for keyword in timeout_keywords): is_session_timeout = True
        elif "error" in page_title.lower() and any(keyword in page_source for keyword in timeout_keywords): is_session_timeout = True

        if is_session_timeout:
            print("[警告] セッションタイムアウトページが検出されました。")
            save_screenshot(driver, "session_timeout_detected", screenshots_dir)
            return True
        else:
            return False
    except (TimeoutException, StaleElementReferenceException):
        return False
    except WebDriverException as e:
        if "invalid session id" in str(e).lower() or "no such window" in str(e).lower():
            print(f"[エラー] セッションタイムアウトチェック中に致命的なWebDriverエラー: {e}")
            raise
        else:
            print(f"[エラー] セッションタイムアウトチェック中に予期せぬWebDriverエラー: {e}")
            save_screenshot(driver, "session_check_webdriver_error", screenshots_dir)
            return False
    except Exception as e:
        print(f"[エラー] セッションタイムアウトチェック中に予期せぬエラー: {e}")
        save_screenshot(driver, "session_check_unknown_error", screenshots_dir)
        traceback.print_exc()
        return False

def initialize_driver(driver_path, headless=False):
    """WebDriver (Chrome) を初期化する"""
    print("\nWebDriverを初期化しています...")
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'normal'
    
    # 共通の最適化設定（ヘッドレスモードの有無に関わらず適用）
    prefs = {
        'profile.default_content_setting_values': { 
            'images': 2,  # 画像を無効化
            'plugins': 2,  # プラグインを無効化
            'popups': 2,   # ポップアップを無効化
            'notifications': 2,  # 通知を無効化
            'automatic_downloads': 2  # 自動ダウンロードを無効化
        },
        'credentials_enable_service': False,
        'profile.password_manager_enabled': False
    }
    options.add_experimental_option('prefs', prefs)
    
    # ヘッドレスモード固有の設定
    if headless:
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--blink-settings=imagesEnabled=false')
        print("ヘッドレスモードで実行します。")
    
    # 共通のパフォーマンス最適化設定
    options.add_argument('--disable-extensions')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-popup-blocking')
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    new_driver = None
    try:
        if driver_path and os.path.exists(driver_path):
            service = Service(executable_path=driver_path)
            new_driver = webdriver.Chrome(service=service, options=options)
            print(f"指定されたChromeDriverを使用: {driver_path}")
        else:
            print("ChromeDriverパス未指定/無効のため、自動検出します。")
            service = Service()
            new_driver = webdriver.Chrome(service=service, options=options)
            print(f"自動検出されたChromeDriverを使用: {service.path}")
        new_driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        new_driver.implicitly_wait(5)
        print("WebDriverの初期化完了。")
        return new_driver
    except Exception as e:
        print(f"[重大エラー] WebDriverの初期化失敗: {e}")
        traceback.print_exc()
        return None


def recover_driver_session():
    """Recover an invalid WebDriver session by reinitializing the WebDriver"""
    print(f"[{time.strftime('%H:%M:%S')}] 🔄 Attempting to recover driver session...")
    try:
        global driver
        
        # Try to close the existing driver if it exists
        try:
            if 'driver' in globals() and driver:
                driver.quit()
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Error closing existing driver: {e}")
        
        # Initialize a new driver
        driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
        if not driver:
            print(f"[{time.strftime('%H:%M:%S')}] ❌ Failed to initialize new driver")
            return False
            
        # Attempt login
        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
            print(f"[{time.strftime('%H:%M:%S')}] ❌ Failed to login with new driver")
            return False
            
        print(f"[{time.strftime('%H:%M:%S')}] ✅ Driver session successfully recovered")
        globals()['driver'] = driver  # Ensure global driver is updated
        return True
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ Session recovery failed: {str(e)}")
        return False

# Add new recovery function here
def recover_webdriver(screenshots_dir):
    """WebDriverをリカバリーし、再ログインを試みる"""
    retries = 3
    
    for attempt in range(retries):
        try:
            print(f"\n[情報] WebDriver再初期化試行 ({attempt + 1}/{retries})...")
            
            # 古いドライバーを閉じる
            try:
                if 'driver' in globals() and driver:
                    driver.quit()
            except Exception as e:
                print(f"[警告] 古いドライバー終了エラー: {e}")
            
            # 新しいドライバーを初期化
            new_driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
            if not new_driver:
                print("[エラー] WebDriver初期化失敗")
                time.sleep(3)
                continue
                
            # ログイン試行
            if not login(new_driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                print("[エラー] ログイン失敗")
                if new_driver:
                    new_driver.quit()
                time.sleep(3)
                continue
                
            print("[成功] WebDriver再初期化とログイン完了")
            return new_driver
            
        except Exception as e:
            print(f"[エラー] WebDriverリカバリー中の予期せぬエラー: {e}")
            traceback.print_exc()
            time.sleep(3)
    
    print("[重大エラー] WebDriverリカバリー失敗")
    return None

# --- ★★★ JSONファイル書き込み関数 (変更なし) ★★★ ---
def write_json_data(data, path):
    """指定されたパスにJSONデータを書き込む"""
    print(f"\n'{path}' へ書き込み中 ({len(data)} 件)...")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode='w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"JSON書き込み完了。")
    except Exception as e:
        print(f"[エラー] JSON書き込みエラー: {e}")

# Missing function that I realized is referenced but wasn't included in the original code
def pause_on_error(error_message, exception=None, screenshot_path=None):
    """エラー発生時に処理を一時停止し、ユーザーに続行するか確認する"""
    print(f"\n[エラー] {error_message}")
    if exception: print(f"例外詳細: {exception}")
    if screenshot_path: print(f"スクリーンショット: {screenshot_path}")
    
    # 常に続行する (自動処理モード)
    return True
    
    # 以下のコードはユーザー確認が必要な場合に使用
    # try:
    #     response = input("\n処理を続行しますか？ (y/n): ").strip().lower()
    #     return response in ('y', 'yes', '')
    # except KeyboardInterrupt:
    #     print("\nキーボード割り込みにより中断。")
    #     return False

# --- ★★★ メイン処理 (逐次処理に戻す) ★★★ ---
if __name__ == "__main__":
    output_dir, logs_dir, screenshots_dir = create_output_dirs(OUTPUT_DIR_NAME)
    resume_checkpoint = load_checkpoint()
    starting_year_index = 0
    starting_field_index = 0
    starting_page_num = 0
    processed_urls = set()
    if resume_checkpoint:
        # ユーザー確認
        resume_choice = input(f"\nチェックポイントが見つかりました (年度: {resume_checkpoint['year']}, 分野: {resume_checkpoint['field_name']}, ページ: {resume_checkpoint['page_num']})。"
                            f"\n再開しますか？ (y/n): ").strip().lower()
        
        if resume_choice in ('y', 'yes', ''):
            # TARGET_YEARSとTARGET_FIELDSからインデックスを検索
            if resume_checkpoint['year'] in TARGET_YEARS:
                starting_year_index = TARGET_YEARS.index(resume_checkpoint['year'])
            else:
                print(f"[警告] チェックポイントの年度 {resume_checkpoint['year']} は現在の対象年度にありません。最初から開始します。")
                
            if resume_checkpoint['field_name'] in TARGET_FIELDS:
                starting_field_index = TARGET_FIELDS.index(resume_checkpoint['field_name'])
            else:
                print(f"[警告] チェックポイントの分野 {resume_checkpoint['field_name']} は現在の対象分野にありません。この年度の最初から開始します。")
                starting_field_index = 0
                
            starting_page_num = resume_checkpoint['page_num']
            processed_urls = set(resume_checkpoint['processed_urls'])
            print(f"\n[情報] チェックポイントから再開: 年度={resume_checkpoint['year']} (インデックス: {starting_year_index}), "
                f"分野={resume_checkpoint['field_name']} (インデックス: {starting_field_index}), ページ={starting_page_num}, 処理済URL数={len(processed_urls)}")
        else:
            print("\n[情報] 最初から開始します。")

    start_time_dt = datetime.datetime.now()
    start_time_dt = datetime.datetime.now()
    output_json_path = os.path.join(output_dir, OUTPUT_JSON_FILE)
    driver = None
    scraped_data_all_years = []
    global_start_time = time.time()
    print(f"スクレイピング開始: {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象年度: {TARGET_YEARS}")
    print(f"対象分野: {TARGET_FIELDS}")
    print(f"出力先JSON: {output_json_path}")
    print(f"並列処理: 無効 (逐次処理)") # 並列処理は無効

    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
    if not driver:
        sys.exit("致命的エラー: WebDriverを初期化できませんでした。")
    try:
        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
            sys.exit("致命的エラー: 初期ログインに失敗しました。")
        print("\n認証情報を抽出中...")
        auth_cookies = extract_auth_cookies(driver)
        if auth_cookies:
            print(f"認証Cookie取得成功: {len(auth_cookies)}個のCookieを共有します")
        else:
            print("[警告] 認証Cookie取得失敗。各スレッドが個別にログインします。")
    except Exception as initial_login_e:
        print(f"致命的エラー: 初期ログイン中に予期せぬ例外が発生: {initial_login_e}")
        traceback.print_exc()
        if driver:
            try:
                save_screenshot(driver, "initial_login_fatal_error", screenshots_dir)
                driver.quit()
            except Exception as qe: print(f"初期ログインエラー後のブラウザ終了時エラー: {qe}")
        sys.exit(1)

# --- メインループ ---
    try:
        year_index = starting_year_index
        while year_index < len(TARGET_YEARS):
            year = TARGET_YEARS[year_index]
            print(f"\n<<<<< {year}年度 の処理開始 >>>>>")
            year_processed_successfully = True

            # すべての年度で標準的なタイムアウト設定を使用
            current_page_timeout = PAGE_LOAD_TIMEOUT
            current_element_timeout = ELEMENT_WAIT_TIMEOUT
            
            # この年度の処理開始フィールドインデックスを設定
            field_index = starting_field_index if year_index == starting_year_index else 0
            
            while field_index < len(TARGET_FIELDS):
                field_name = TARGET_FIELDS[field_index]
                print(f"\n===== 分野: {field_name} ({year}年度) の処理開始 =====")
                field_processed_successfully = True
                field_total_attempts = 0
                field_error_count = 0
                consecutive_errors = 0
                ttck_error_count = 0  # TTCK科目専用のエラーカウンター
                
                # この分野の処理済みURL（チェックポイントからロード、または新規作成）
                if year_index == starting_year_index and field_index == starting_field_index:
                    opened_links_this_year_field = processed_urls
                    # この分野の開始ページ番号（チェックポイントからロード、または最初から）
                    last_processed_page_num = starting_page_num
                else:
                    opened_links_this_year_field = set()
                    last_processed_page_num = 0
                    
                # チェックポイントを使用したのでリセット（次の分野と年度では最初から開始するため）
                if year_index == starting_year_index and field_index == starting_field_index:
                    starting_page_num = 0

                try:
                    if check_session_timeout(driver, screenshots_dir):
                        print("セッションタイムアウト検出。再ログイン試行...")
                        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir):
                            print("[エラー] 再ログイン失敗。この分野をスキップします。")
                            field_index += 1; continue

                    try:
                        current_url_check = driver.current_url
                        if "gslbs.keio.jp/syllabus/search" not in current_url_check:
                            print("検索ページ以外にいるため、検索ページに移動します。")
                            driver.get('https://gslbs.keio.jp/syllabus/search')
                            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.url_contains("gslbs.keio.jp/syllabus/search"))
                            time.sleep(MEDIUM_WAIT)
                    except WebDriverException as e_url_check:
                        screenshot_path = save_screenshot(driver, f"url_check_error_{year}_{field_name}", screenshots_dir)
                        print(f"[警告] 現在のURL確認中にエラー: {e_url_check}。")
                        
                        if not pause_on_error("WebDriver exception during URL check", e_url_check, screenshot_path):
                            print("ユーザーによる中断。スクリプトを終了します。")
                            sys.exit(1)
                        
                        raise InvalidSessionIdException("URL check failed, likely closed window.") from e_url_check

                    # --- 検索条件設定 (JS高速化 + Seleniumフォールバック) ---
                    js_search_success = False
                    try: # JavaScriptでの設定試行
                        fast_search_js = """
                            async function setSearchCriteria(year, fieldName) {
                                try {
                                    var yearSelect = document.querySelector('select[name="KEYWORD_TTBLYR"]');
                                    if (yearSelect) { yearSelect.value = year; yearSelect.dispatchEvent(new Event('change', {bubbles:true})); }
                                    else { console.error('Year select not found'); return false; }

                                    var toggleButton = document.querySelector('button[data-target*="screensearch-cond-option-toggle-target"]');
                                    if (toggleButton) {
                                        var toggleTarget = document.querySelector(toggleButton.getAttribute('data-target'));
                                        if (toggleTarget && !toggleTarget.classList.contains('show')) {
                                            toggleButton.click(); await new Promise(r => setTimeout(r, 700));
                                        }
                                    }

                                    var fieldSelect = document.querySelector('select[name="KEYWORD_FLD1CD"]');
                                    if (fieldSelect) {
                                        let fieldFound = false;
                                        for (let i = 0; i < fieldSelect.options.length; i++) {
                                            if (fieldSelect.options[i].text.trim() === fieldName) {
                                                fieldSelect.selectedIndex = i; fieldSelect.dispatchEvent(new Event('change', {bubbles:true}));
                                                fieldFound = true; break;
                                            }
                                        }
                                        if (!fieldFound) console.warn('Field option not found: ' + fieldName);
                                    } else { console.error('Field select not found'); return false; }

                                    var checkbox = document.querySelector('input[name="KEYWORD_LVL"][value="3"]');
                                    if (checkbox && checkbox.checked) { checkbox.checked = false; checkbox.dispatchEvent(new Event('change', {bubbles:true})); }

                                    return true;
                                } catch (error) { console.error('Error in setSearchCriteria:', error); return false; }
                            }
                            return await setSearchCriteria(arguments[0], arguments[1]);
                        """
                        result = driver.execute_script(fast_search_js, str(year), field_name)
                        if result:
                            print(f"   JavaScriptで検索条件を一括設定しました（年度: {year}, 分野: {field_name}）")
                            time.sleep(MEDIUM_WAIT); js_search_success = True
                        else: print(f"   JavaScript検索設定で問題発生。通常方法で試行します。")
                    except Exception as js_err: print(f"   JavaScript検索設定失敗: {js_err}。通常方法で試行します。")

                    if not js_search_success: # Seleniumでの設定 (フォールバック)
                        # 年度選択
                        year_select_xpath = "//select[@name='KEYWORD_TTBLYR']"
                        year_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, year_select_xpath)))
                        if not select_option_by_text(driver, year_select_element, str(year)):
                            print(f"     [警告] 年度 '{year}' の選択に失敗。この分野をスキップします。")
                            save_screenshot(driver, f"year_selection_failed_{year}_{field_name}", screenshots_dir); field_index += 1; continue
                        print(f"   年度 '{year}' を選択しました。"); time.sleep(SHORT_WAIT)
                        # 詳細オプション展開
                        try:
                            adv_button_xpath = "//button[contains(@data-target, 'screensearch-cond-option-toggle-target')]"
                            advanced_options_button = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, adv_button_xpath)))
                            target_selector = advanced_options_button.get_attribute('data-target')
                            target_element = driver.find_element(By.CSS_SELECTOR, target_selector)
                            if advanced_options_button and not target_element.is_displayed():
                                print("   展開ボタンをクリックして詳細オプションを表示します。")
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", advanced_options_button); time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", advanced_options_button); time.sleep(1.5)
                            # else: print("   詳細オプションは既に展開済み、またはボタンが見つかりません。") # ログ省略可
                        except Exception as e: print(f"   詳細オプション展開ボタンの操作中にエラー: {e}")
                        # 分野選択
                        field_select_xpath = "//select[@name='KEYWORD_FLD1CD']"
                        max_retries = 3; field_selected = False
                        for retry in range(max_retries):
                            try:
                                field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.element_to_be_clickable((By.XPATH, field_select_xpath)))
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", field_select_element); time.sleep(1.0)
                                if select_option_by_text(driver, field_select_element, field_name):
                                    print(f"   分野 '{field_name}' を選択しました。"); time.sleep(MEDIUM_WAIT); field_selected = True; break
                                else: print(f"   分野 '{field_name}' の選択に失敗（試行 {retry+1}/{max_retries}）")
                            except Exception as e:
                                print(f"   リトライ {retry+1}/{max_retries}: 分野 '{field_name}' 選択中にエラー: {e}")
                                if retry < max_retries - 1:
                                     print("      ページをリフレッシュして再試行します...")
                                     driver.refresh()
                                     WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.TAG_NAME, "body"))); time.sleep(MEDIUM_WAIT)
                                     year_select_element_retry = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.XPATH, year_select_xpath)))
                                     select_option_by_text(driver, year_select_element_retry, str(year)); time.sleep(SHORT_WAIT)
                                else: print("      リフレッシュ後の再試行も失敗しました。")
                                time.sleep(MEDIUM_WAIT)
                        if not field_selected:
                             print(f"     [警告] 分野 '{field_name}' の選択が {max_retries} 回失敗しました。スキップします。")
                             save_screenshot(driver, f"field_selection_failed_{field_name}_{year}", screenshots_dir); field_index += 1; continue
                        # 学年チェックボックス解除
                        try:
                            cb_xpath = "//input[@name='KEYWORD_LVL' and @value='3']"
                            cb = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, cb_xpath)))
                            if cb.is_selected():
                                print("   学年「3年」のチェックを外します。")
                                driver.execute_script("arguments[0].click();", cb); time.sleep(0.5)
                        except TimeoutException: pass
                        except Exception as e_cb: print(f"           学年チェックボックス処理エラー: {e_cb}")

                    # --- 検索実行 ---
                    search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(), '検索')]"
                    search_button = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.element_to_be_clickable((By.XPATH, search_xpath)))
                    print("   検索ボタンをクリックします...")
                    if not click_element(driver, search_button):
                        print("     [エラー] 検索ボタンクリック失敗。この分野をスキップします。")
                        save_screenshot(driver, f"search_button_click_failed_{year}_{field_name}", screenshots_dir); field_index += 1; continue

                    # --- 結果表示待機 ---
                    # 拡張された結果インジケーターXPath
                    result_indicator_xpath = (
                        "//a[contains(@class, 'syllabus-detail')] | "
                        "//a[contains(@class, 'btn-info')] | "
                        "//div[contains(text(), '該当するデータはありません')] | "
                        "//ul[contains(@class, 'pagination')] | "
                        "//table[contains(@class, 'search-result')] | "
                        "//div[contains(text(), '件') and contains(text(), '中')] | "
                        "//div[@class='search-result-list']"
                    )
                    print("   検索結果表示待機中...")
                    # 検索結果の待機処理を改善（最大3回リトライ）
                    max_search_retries = 3
                    for search_retry in range(max_search_retries):
                        try:
                            print(f"   検索結果表示待機中... (試行 {search_retry + 1}/{max_search_retries})")
                            # 一旦短いタイムアウトで試してみる
                            try:
                                WebDriverWait(driver, min(30, current_element_timeout/2)).until(
                                    EC.presence_of_element_located((By.XPATH, result_indicator_xpath))
                                )
                                print("   検索結果表示完了。")
                                break
                            except TimeoutException:
                                # ページが完全に読み込まれていない可能性があるため、リロード
                                if search_retry < max_search_retries - 1:
                                    print(f"   検索結果表示タイムアウト、ページをリロードして再試行します... ({search_retry + 1}/{max_search_retries})")
                                    driver.refresh()
                                    time.sleep(MEDIUM_WAIT * 2)
                                    
                                    # 検索条件を再設定して検索ボタンを再度クリック
                                    if not js_search_success:
                                        # 年度選択
                                        year_select_xpath = "//select[@name='KEYWORD_TTBLYR']"
                                        year_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                                            EC.presence_of_element_located((By.XPATH, year_select_xpath))
                                        )
                                        select_option_by_text(driver, year_select_element, str(year))
                                        time.sleep(MEDIUM_WAIT)
                                        
                                        # 分野選択
                                        field_select_xpath = "//select[@name='KEYWORD_FLD1CD']"
                                        field_select_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                                            EC.presence_of_element_located((By.XPATH, field_select_xpath))
                                        )
                                        select_option_by_text(driver, field_select_element, field_name)
                                        time.sleep(MEDIUM_WAIT)
                                    
                                    # 検索ボタンを再クリック
                                    search_xpath = "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE'] | //button[contains(text(), '検索')]"
                                    search_button = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                                        EC.element_to_be_clickable((By.XPATH, search_xpath))
                                    )
                                    click_element(driver, search_button)
                                    
                                    # 長めのタイムアウトで最終試行
                                    if search_retry == max_search_retries - 2:
                                        WebDriverWait(driver, current_element_timeout).until(
                                            EC.presence_of_element_located((By.XPATH, result_indicator_xpath))
                                        )
                                        print("   検索結果表示完了。")
                                        break
                                else:
                                    # 最終試行でもタイムアウトした場合
                                    raise TimeoutException(f"検索結果の表示に {max_search_retries} 回失敗しました")
                        except TimeoutException as e_timeout:
                            if search_retry == max_search_retries - 1:
                                print(f"     [エラー] 検索結果が表示されません。この分野をスキップします。")
                                save_screenshot(driver, f"search_timeout_{year}_{field_name}", screenshots_dir)
                                field_index += 1
                                field_processed_successfully = False
                                year_processed_successfully = False
                                break
                        except Exception as e_search:
                            print(f"     [エラー] 検索処理中に予期せぬエラー: {e_search}")
                            save_screenshot(driver, f"search_error_{year}_{field_name}", screenshots_dir)
                            field_index += 1
                            field_processed_successfully = False
                            year_processed_successfully = False
                            traceback.print_exc()
                            break

                    # オリジナルコードの続き (if field_processed_successfully から)
                    time.sleep(MEDIUM_WAIT); print("   検索結果表示完了。")

                    # --- 該当なしチェック ---
                    try:
                        no_result_element = driver.find_element(By.XPATH, "//div[contains(text(), '該当するデータはありません')]")
                        if no_result_element.is_displayed():
                            print(f"   [情報] {year}年度、分野 '{field_name}' に該当データなし。")
                            field_index += 1; continue
                    except NoSuchElementException: pass

                    # --- ソート順変更 (科目名順) ---
                    try:
                        sort_xpath = "//select[@name='SEARCH_RESULT_NARABIJUN']"
                        sort_element = WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, sort_xpath)))
                        current_sort_value = Select(sort_element).first_selected_option.get_attribute('value')
                        if current_sort_value != '2':
                            print("   ソート順を「科目名順」に変更試行...")
                            if not select_option_by_text(driver, sort_element, "科目名順"):
                                try: Select(sort_element).select_by_value("2"); print("           ソート順を Value='2' で選択しました。")
                                except Exception as e_sort_val:
                                    print(f"           [警告] Value='2'でのソート失敗: {e_sort_val}。JSで試行...")
                                    try: driver.execute_script("arguments[0].value = '2'; arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", sort_element); print("           JSでソート順 Value='2' を設定しました。")
                                    except Exception as e_js: print(f"           [警告] JSでのソートも失敗: {e_js}")
                            else: print("           ソート順を「科目名順」で選択しました。")
                            time.sleep(MEDIUM_WAIT)
                            WebDriverWait(driver, current_element_timeout).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                            time.sleep(MEDIUM_WAIT)
                        # else: print("   ソート順は既に「科目名順」です。") # ログ省略可
                    except TimeoutException: pass
                    except Exception as e_sort: print(f"   [警告] ソート設定エラー: {e_sort}")

                    # --- ページネーションループ (逐次処理) ---
                    last_processed_page_num = 0
                    processed_page_numbers = set()  # Add this to track which pages we've already processed

                    while True:
                        print(f"\n     --- ページネーションブロック処理開始 (最終処理ページ: {last_processed_page_num}) ---")
                        pagination_processed_in_block = False
                        current_page_links_processed_in_block = set()

                        # --- 1. アクティブページ処理 ---
                        current_active_page_num = -1
                        try:
                            pagination_container = WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]")))
                            try:
                                active_page_element = pagination_container.find_element(By.XPATH, ".//li[contains(@class, 'active')]/span | .//li[contains(@class, 'active')]/a")
                                current_active_page_num = int(normalize_text(active_page_element.text))
                                print(f"         現在のアクティブページ: {current_active_page_num}")
                            except (NoSuchElementException, ValueError) as e_active:
                                print(f"         アクティブページ番号の取得に失敗: {e_active}")
                                if last_processed_page_num == 0: print("         最初のページ(1)として処理を試みます..."); current_active_page_num = 1
                                else: print("         [エラー] アクティブページを特定できず、処理を続行できません。"); field_processed_successfully = False; year_processed_successfully = False; break

                            # Add check for already processed pages to avoid infinite loops
                            if current_active_page_num in processed_page_numbers:
                                print(f"         ページ {current_active_page_num} は既に処理済みです。次のページを試行します。")
                            elif current_active_page_num > 0:  # Don't rely on last_processed_page_num check
                                print(f"         ページ {current_active_page_num} を処理します...")
                                syllabus_link_xpath = ""
                                # For 2025 and later
                                if year >= 2025:
                                    # 2025年度以降の新システム用
                                    syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]"
                                else:
                                    # 2024年度以前の旧システム用
                                    syllabus_link_xpath = (
                                        "//a[contains(@class, 'btn-info')] | "
                                        "//a[contains(@class, 'fa-book')] | "
                                        "//td//a[contains(@href, 'syllabus')] | "
                                        "//td//a[contains(@href, 'courses/2024')] | "
                                        "//a[contains(@title, 'シラバス')] | "
                                        "//span[2]/a[contains(@href, 'syllabus') or contains(@href, 'courses')]"
                                    )

                                urls_on_page = []
                                buttons_on_page = []
                                processed_count_on_page = 0

                                try:
                                    # まず一般的なリンクがあるかを確認
                                    WebDriverWait(driver, MEDIUM_WAIT).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
                                    print("         ページの完全なロードを待機中...")
                                    time.sleep(2)  # シラバスリンク抽出前に2秒の追加待機
                                    # すべてのリンクを取得して調査
                                    all_links = driver.find_elements(By.TAG_NAME, "a")
                                    print(f"         ページ上のリンク数: {len(all_links)}")
                                    
                                    # サンプルリンクを表示
                                    for i, link in enumerate(all_links[:5]):
                                        link_text = link.text.strip() if link.text else "テキストなし"
                                        link_class = link.get_attribute("class") or "クラスなし"
                                        link_href = link.get_attribute("href") or "リンクなし"
                                        link_onclick = link.get_attribute("onclick") or "なし"
                                        print(f"         リンク{i+1}: テキスト={link_text}, クラス={link_class}, URL={link_href}, onClick={link_onclick}")
                                    
                                    # シラバス詳細リンクの検索
                                    # IMPORTANT: Replace these lines with more comprehensive syllabus link XPath from csv10.py
                                    if year >= 2025:
                                        # 2025年度以降の新システム用
                                        syllabus_link_xpath = "//a[contains(@class, 'syllabus-detail')]"
                                    else:
                                        # 2024年度以前の旧システム用
                                        syllabus_link_xpath = (
                                            "//a[contains(@class, 'btn-info')] | "
                                            "//a[contains(@class, 'fa-book')] | "
                                            "//td//a[contains(@href, 'syllabus')] | "
                                            "//td//a[contains(@href, 'courses/2024')] | "
                                            "//a[contains(@title, 'シラバス')] | "
                                            "//span[2]/a[contains(@href, 'syllabus') or contains(@href, 'courses')]"
                                        )
                                        
                                    buttons_on_page = driver.find_elements(By.XPATH, syllabus_link_xpath)
                                    print(f"         シラバスリンク数: {len(buttons_on_page)}")
                                    
                                    # onclick属性からURLを取得（JSを使用する場合のため）
                                    try:
                                        # Use ONLY JavaScript as the URL detection method
                                        js_script = """
                                        // Target all syllabus detail links
                                        const syllabusUrls = [];

                                        // First approach: Get all links with syllabus-detail class (for 2025+ system)
                                        const detailLinks = document.querySelectorAll('a.syllabus-detail');
                                        detailLinks.forEach(link => {
                                            if (link.href) {
                                                syllabusUrls.push(link.href);
                                            }
                                        });

                                        // Second approach: Get all blue buttons with class btn-info (for older system)
                                        const blueButtons = document.querySelectorAll('a.btn-info, button.btn-info');
                                        blueButtons.forEach(button => {
                                            if (button.href) {
                                                syllabusUrls.push(button.href);
                                            }
                                        });

                                        // Third approach: Look for syllabus links in table cells
                                        document.querySelectorAll('td a').forEach(link => {
                                            if (link.href && (link.href.includes('syllabus') || 
                                                            link.href.includes('entno=') || 
                                                            link.href.includes('courses'))) {
                                                syllabusUrls.push(link.href);
                                            }
                                        });

                                        // Fourth approach: Check for onclick handlers on buttons
                                        document.querySelectorAll('a[onclick], button[onclick]').forEach(el => {
                                            if (el.onclick) {
                                                const onclickStr = el.onclick.toString();
                                                if (onclickStr.includes('syllabus') || onclickStr.includes('detail')) {
                                                    const matches = onclickStr.match(/window\.open\(['"]([^'"]+)['"]/);
                                                    if (matches && matches[1]) {
                                                        syllabusUrls.push(matches[1]);
                                                    }
                                                }
                                            }
                                        });

                                        return [...new Set(syllabusUrls)];
                                        """
                                        urls_on_page = driver.execute_script(js_script)
                                        print(f"         JavaScriptで検出したURL数: {len(urls_on_page)}")
                                        for i, url in enumerate(urls_on_page[:5]):
                                            print(f"         JS-URL{i+1}: {url}")
                                        
                                        # Basic filtering to remove non-syllabus URLs
                                        filtered_urls = []
                                        for url in urls_on_page:
                                            if url and not url.endswith('#') and not '/result#' in url:
                                                if year <= 2024:
                                                    if ("syllabus" in url or "courses" in url or "entno=" in url) and not "search" in url:
                                                        filtered_urls.append(url)
                                                else:
                                                    # For 2025 and later, just check for key identifiers
                                                    if "detail" in url or "syllabus" in url or "entno=" in url:
                                                        filtered_urls.append(url)
                                        
                                        urls_on_page = filtered_urls
                                        print(f"         フィルタリング後の有効URL数: {len(urls_on_page)}")
                                        for i, url in enumerate(urls_on_page[:5]):
                                            print(f"         有効URL {i+1}: {url}")
                                        
                                    except Exception as js_e:
                                        print(f"         [警告] JavaScript URL抽出エラー: {js_e}")
                                        urls_on_page = []
                                    
                                    
                                    
                                    # 重複を削除
                                    print(f"         最終処理対象URL数: {len(urls_on_page)}")
                                    for i, url in enumerate(urls_on_page):
                                        print(f"         最終URL {i+1}: {url}")
                                    # シラバス詳細ページのURLのみをフィルタリングして残す
                                    filtered_urls = []
                                    for url in urls_on_page:
                                        if not url.endswith('#') and not '/result#' in url:
                                            if year <= 2024:
                                                if ("syllabus" in url or "courses" in url or "entno=" in url) and not "search" in url:
                                                    filtered_urls.append(url)
                                            else:
                                                filtered_urls.append(url)
                                        else:
                                            print(f"         スキップ: ナビゲーションハッシュURL: {url}")

                                    urls_on_page = filtered_urls

                                    # フィルター後のURLに置き換え
                                    urls_on_page = filtered_urls
                                    print(f"         フィルタリング後の有効URL数: {len(urls_on_page)}")
                                    for i, url in enumerate(urls_on_page[:5]):  # 最初の5つのみ表示
                                        print(f"         有効URL {i+1}: {url}")
                                    print(f"         最終的に抽出したURL数: {len(urls_on_page)}")
                                    for i, url in enumerate(urls_on_page[:5]):
                                        print(f"         URL{i+1}: {url}")

                                    # Add debug logging for URL detection
                                    if not urls_on_page:
                                        print("         [警告] ページ上のシラバスリンクが見つかりませんでした。HTML構造を出力します。")
                                        try:
                                            # ページの主要構造を出力
                                            js_debug = """
                                            const tables = document.querySelectorAll('table');
                                            let tableInfo = [];
                                            tables.forEach((table, idx) => {
                                                tableInfo.push({
                                                    index: idx,
                                                    rows: table.rows.length,
                                                    links: table.querySelectorAll('a').length,
                                                    buttons: table.querySelectorAll('button').length
                                                });
                                            });
                                            return {
                                                tables: tableInfo,
                                                allLinks: document.querySelectorAll('a').length,
                                                allButtons: document.querySelectorAll('button').length,
                                                bodyHTML: document.body.innerHTML.substring(0, 500) + '...'  // 先頭500文字のみ
                                            };
                                            """
                                            debug_info = driver.execute_script(js_debug)
                                            print(f"         テーブル数: {len(debug_info['tables'])}")
                                            for i, table in enumerate(debug_info['tables']):
                                                print(f"         テーブル #{i+1}: {table['rows']}行, {table['links']}リンク, {table['buttons']}ボタン")
                                            print(f"         総リンク数: {debug_info['allLinks']}, 総ボタン数: {debug_info['allButtons']}")
                                            print(f"         HTML構造プレビュー: {debug_info['bodyHTML']}")
                                            
                                            # スクリーンショットを保存
                                            save_screenshot(driver, f"no_links_found_{year}_{field_name}_page{current_active_page_num}", screenshots_dir)
                                        except Exception as debug_e:
                                            print(f"         [警告] デバッグ情報取得エラー: {debug_e}")
                                    
                                    if len(urls_on_page) > 0:
                                        print(f"         {len(urls_on_page)} 件のURLを処理します...")
                                        processed_count_on_page = 0
                                        field_total_attempts = 0
                                        field_error_count = 0
                                        consecutive_errors = 0
                                        
                                        for index, syllabus_url in enumerate(urls_on_page):
                                            # Check if this URL has already been processed
                                            if syllabus_url in opened_links_this_year_field:
                                                print(f"           URL {index + 1}/{len(urls_on_page)}: {syllabus_url} は既に処理済みのためスキップします")
                                                continue

                                            print(f"\n           詳細処理 {index + 1}/{len(urls_on_page)}: {syllabus_url}")
                                            syllabus_details = None
                                            
                                            try:
                                                # Store the main window handle first for reliable tab management
                                                main_window = driver.current_window_handle
                                                
                                                if check_session_timeout(driver, screenshots_dir):
                                                    raise InvalidSessionIdException("Session timeout before detail fetch")
                                                
                                                # Open a new tab instead of navigating in the current tab
                                                print(f"           新しいタブを開いて詳細ページを表示します...")
                                                driver.switch_to.new_window('tab')
                                                detail_tab = driver.current_window_handle
                                                
                                                # Navigate to the syllabus URL in the new tab
                                                driver.get(syllabus_url)
                                                
                                                # Process the page
                                                WebDriverWait(driver, min(30, ELEMENT_WAIT_TIMEOUT)).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                                                print(f"           詳細ページ読み込み完了。処理開始...")
                                                time.sleep(MEDIUM_WAIT)
                                                
                                                # Get syllabus details - this function already handles both Japanese and English data
                                                syllabus_details = get_syllabus_details(driver, year, screenshots_dir)
                                                
                                                # Close the detail tab and switch back to main window
                                                print(f"           詳細ページ処理完了。タブを閉じて検索結果に戻ります...")
                                                driver.close()
                                                driver.switch_to.window(main_window)
                                                time.sleep(SHORT_WAIT)

                                                # Only mark as processed if we actually got details
                                                if syllabus_details:
                                                    print(f"           詳細情報取得成功。データ追加します。")
                                                    # Extract identifiers for logging
                                                    course_id = syllabus_details.get('course_id', 'unknown')
                                                    course_name = syllabus_details.get('translations', {}).get('ja', {}).get('name', 'Unknown')
                                                    professor = syllabus_details.get('professor_ja', 'Unknown')
                                                    field = syllabus_details.get('field_ja', 'Unknown')
                                                    
                                                    # Add to results and mark as processed
                                                    scraped_data_all_years.append(syllabus_details)
                                                    opened_links_this_year_field.add(syllabus_url)
                                                    processed_count_on_page += 1
                                                    consecutive_errors = 0
                                                    
                                                    print(f"           ✅ 成功: ID:{course_id} | {course_name} | Prof:{professor} | Field:{field}")
                                                else:
                                                    print(f"           詳細情報の取得に失敗しました。")
                                                    field_error_count += 1
                                                    consecutive_errors += 1
                                            except InvalidSessionIdException as e_session:
                                                print(f"           [エラー] セッションエラー: {e_session}")
                                                
                                                if recover_driver_session():
                                                    print(f"           セッションを回復しました。次のURLに進みます...")
                                                    driver = globals()['driver']  # Get the new driver
                                                    # Update main window in case of session recovery
                                                    main_window = driver.current_window_handle
                                                else:
                                                    print(f"           セッション回復に失敗しました。処理を中断します。")
                                                    field_error_count += 1
                                                    consecutive_errors += 1
                                            except Exception as e:
                                                print(f"           [エラー] 詳細ページ処理中にエラー: {e}")
                                                
                                                # Try to close the tab and return to main window
                                                try:
                                                    driver.close()
                                                    driver.switch_to.window(main_window)
                                                except Exception as tab_error:
                                                    print(f"           [警告] タブを閉じる際にエラー: {tab_error}")
                                                    
                                                    # Attempt to recover if tab management failed
                                                    try:
                                                        # Check if we have multiple windows open and need to close extras
                                                        if len(driver.window_handles) > 1:
                                                            print(f"           複数のウィンドウが開いています。元のウィンドウに戻ります...")
                                                            for handle in driver.window_handles:
                                                                if handle != main_window:
                                                                    driver.switch_to.window(handle)
                                                                    driver.close()
                                                            driver.switch_to.window(main_window)
                                                        else:
                                                            # If we're down to one window, it might not be the search results page
                                                            print(f"           検索ページに戻ります...")
                                                            driver.get('https://gslbs.keio.jp/syllabus/search')
                                                            WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
                                                                EC.presence_of_element_located((By.XPATH, "//button[@data-action_id='SYLLABUS_SEARCH_KEYWORD_EXECUTE']"))
                                                            )
                                                            js_script = """
                                                                function getPageData() {
                                                                    const data = {};
                                                                    // Process Japanese page data
                                                                    try {
                                                                        data.course_name = document.querySelector('.class-name')?.textContent.trim() || "名称不明";
                                                                        data.semester = document.querySelector('tr th:contains("年度・学期") + td')?.textContent.trim() || "学期不明";
                                                                        data.professor = document.querySelector('tr th:contains("担当者名") + td')?.textContent.trim() || "";
                                                                        data.credits = document.querySelector('tr th:contains("単位") + td')?.textContent.trim() || "単位不明";
                                                                        data.field = document.querySelector('tr th:contains("分野") + td')?.textContent.trim() || "分野不明";
                                                                        data.location = document.querySelector('tr th:contains("教室") + td, tr th:contains("開講場所") + td')?.textContent.trim() || "教室不明";
                                                                        data.day_period = document.querySelector('tr th:contains("曜日時限") + td')?.textContent.trim() || "曜日時限不明";
                                                                        data.selection_method = document.querySelector('tr th:contains("選抜方法") + td')?.textContent.trim() || "";
                                                                        data.class_format = document.querySelector('tr th:contains("授業実施形態") + td')?.textContent.trim() || "";
                                                                    } catch(e) {
                                                                        console.error("Error extracting Japanese data:", e);
                                                                    }
                                                                    return data;
                                                                }
                                                                return getPageData();
                                                            """
                                                            ja_data = driver.execute_script(js_script)
                                                            driver.execute_script(js_script, str(year), field_name)
                                                            time.sleep(MEDIUM_WAIT)
                                                    except Exception as recovery_error:
                                                        print(f"           [警告] リカバリー中にエラー: {recovery_error}")
                                                        field_error_count += 1
                                                        consecutive_errors += 1
                                                        continue
                                                        
                                                field_error_count += 1
                                                consecutive_errors += 1
                                            
                                            # Check consecutive errors threshold
                                            if ENABLE_AUTO_HALT and consecutive_errors >= CONSECUTIVE_ERROR_THRESHOLD:
                                                print(f"           [!!!] {consecutive_errors}回の連続エラーが発生しました。WebDriverを再初期化します...")
                                                if recover_driver_session():
                                                    consecutive_errors = 0
                                                    print("           ✅ WebDriver再初期化に成功しました。続行します。")
                                                    # Reload search page and redo search after full recovery
                                                    driver = globals()['driver']
                                                    main_window = driver.current_window_handle
                                                else:
                                                    print("           ❌ WebDriver再初期化に失敗しました。処理を中断します。")
                                                    break
                                            
                                            # Brief pause between URLs to avoid hammering the server
                                            time.sleep(SHORT_WAIT)

                                    if processed_count_on_page > 0:
                                        save_checkpoint(year, field_name, current_active_page_num, opened_links_this_year_field)
                                        print(f"         ページ {current_active_page_num} の処理が完了しました: {processed_count_on_page}件処理済")
                                    else:
                                        print(f"         処理対象のURLが見つかりませんでした")

                                except TimeoutException:
                                    print(f"         [警告] シラバスリンクの読み込みタイムアウト")
                                    buttons_on_page = []
                                except Exception as e:
                                    print(f"         [警告] シラバスリンクの取得エラー: {e}")
                                    traceback.print_exc()
                                    buttons_on_page = []

                                # Mark this page as processed and update the last processed page number
                                processed_page_numbers.add(current_active_page_num)
                                last_processed_page_num = current_active_page_num
                                current_page_links_processed_in_block.add(current_active_page_num)
                                pagination_processed_in_block = True
                                print(f"         ページ {current_active_page_num} の処理が完了しました。")

                            # --- 2. クリック可能なページ番号処理 ---
                            page_number_elements_info = []
                            page_number_links_xpath = ".//li[not(contains(@class, 'active')) and not(contains(@class, 'disabled'))]/a[number(text()) = number(text())]"
                            try:
                                pagination_container_refresh = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]")))
                                page_number_elements = pagination_container_refresh.find_elements(By.XPATH, page_number_links_xpath)
                            except (TimeoutException, NoSuchElementException): page_number_elements = []

                            for link_element in page_number_elements:
                                try:
                                    page_num = int(normalize_text(link_element.text))
                                    # Only add unprocessed pages to the navigation targets
                                    if page_num not in processed_page_numbers and page_num not in current_page_links_processed_in_block:
                                        page_number_elements_info.append((page_num, link_element))
                                except (ValueError, StaleElementReferenceException): continue

                        except (NoSuchElementException, TimeoutException) as e_paginate_find:
                            if len(processed_page_numbers) <= 1 and current_active_page_num <= 1:
                                print("         ページネーション要素が見つからないか、最初のページのみです。")
                                if current_active_page_num > 0: pagination_processed_in_block = True
                            else: print(f"         [警告] ページネーション要素の取得に失敗: {e_paginate_find}。")
                            if len(processed_page_numbers) > 0 and all(p in processed_page_numbers for p in range(1, max(processed_page_numbers) + 1)):
                                print("         すべてのページを処理しました。ページネーションを終了します。")
                                break
                            break
                        except Exception as e_paginate_outer:
                            print(f"         [エラー] ページネーション処理中に予期せぬエラー: {e_paginate_outer}"); traceback.print_exc()
                            field_processed_successfully = False; year_processed_successfully = False; break

                        # Sort page elements by number to ensure we process them in order
                        page_number_elements_info.sort(key=lambda x: x[0])
                        clicked_page_link = False
                        
                        if page_number_elements_info:
                            print(f"         未処理ページ: {', '.join(str(p[0]) for p in page_number_elements_info)}")
                            for page_num, link_element_stub in page_number_elements_info:
                                print(f"         ページ {page_num} への遷移を試みます...")
                                try:
                                    link_to_click = WebDriverWait(driver, SHORT_WAIT).until(EC.element_to_be_clickable((By.XPATH, f"//ul[contains(@class, 'pagination')]//li/a[normalize-space(text())='{page_num}']")))
                                    if click_element(driver, link_to_click):
                                        print(f"         ページ {page_num} へ遷移。結果待機中...")
                                        WebDriverWait(driver, current_element_timeout).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                        time.sleep(MEDIUM_WAIT)
                                        clicked_page_link = True
                                        break
                                    else: print(f"         [警告] ページ {page_num} のクリックに失敗。次のページ番号を試します。"); continue
                                except (TimeoutException, StaleElementReferenceException, NoSuchElementException) as e_click:
                                    print(f"         [警告] ページ {page_num} の検索/クリック中にエラー: {e_click}。次のページ番号を試します。"); continue
                                except Exception as e_proc_outer:
                                    print(f"         [エラー] ページ {page_num} の処理中に予期せぬエラー: {e_proc_outer}"); traceback.print_exc()
                                    field_processed_successfully = False; year_processed_successfully = False; break

                        if not field_processed_successfully: break
                        if clicked_page_link: continue

                        # --- 3. 「次へ」ボタン処理 - only if no other pages to process ---
                        if not clicked_page_link and not page_number_elements_info:
                            try:
                                pagination_container_next = WebDriverWait(driver, SHORT_WAIT).until(EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]")))
                                next_xpath = ".//li[not(contains(@class, 'disabled'))]/a[contains(text(), '次') or contains(., 'Next')]"
                                next_button = pagination_container_next.find_element(By.XPATH, next_xpath)
                                print(f"\n         「次へ」ボタンを検出しました。クリックを試みます...")
                                if click_element(driver, next_button):
                                    print("         「次へ」をクリックしました。結果待機中...")
                                    WebDriverWait(driver, current_element_timeout).until(EC.presence_of_element_located((By.XPATH, result_indicator_xpath)))
                                    time.sleep(MEDIUM_WAIT)
                                    pagination_processed_in_block = True
                                    continue
                                else: print("         [警告] 「次へ」ボタンのクリックに失敗。ページネーションを終了します。"); break
                            except (NoSuchElementException, TimeoutException):
                                print(f"\n         「次へ」ボタンが見つからないか無効です。すべてのページを処理完了しました。"); break
                            except Exception as e_next:
                                print(f"         [エラー] 「次へ」ボタンの検索/クリック中にエラー: {e_next}。ページネーションを終了します。"); traceback.print_exc(); break
                                
                        # --- ページネーションループ判定 ---
                        if not pagination_processed_in_block and len(page_number_elements_info) == 0:
                            print("         このブロックでページ処理が行われず、未処理ページもありません。ページネーションを終了します。")
                            break

                except (InvalidSessionIdException, NoSuchWindowException) as e_session_field:
                    print(f"\n[!!!] 分野 '{field_name}' ({year}年度) 処理中セッション/ウィンドウエラー: {e_session_field}。WebDriver再起動試行。")
                    if driver:
                        try: driver.quit()
                        except Exception as quit_err: print(f" WebDriver終了エラー: {quit_err}")
                    driver = None
                    driver = initialize_driver(CHROME_DRIVER_PATH, HEADLESS_MODE)
                    # Rest of existing code...
                    if not driver: print("[!!!] WebDriver再初期化失敗。スクリプトを終了します。"); raise Exception("WebDriver再初期化失敗。")
                    try:
                        if not login(driver, USER_EMAIL, USER_PASSWORD, screenshots_dir): print("[!!!] 再ログイン失敗。スクリプトを終了します。"); raise Exception("再ログイン失敗。")
                    except Exception as relogin_e: print(f"[!!!] 再ログイン中にエラー: {relogin_e}"); raise
                    print(f" WebDriver再起動・再ログイン完了。分野 '{field_name}' ({year}年度) 再試行。")
                    field_index -= 1; field_processed_successfully = False; year_processed_successfully = False
                except Exception as e_field_main:
                    print(f"     [エラー] 分野 '{field_name}' ({year}年度) 処理中エラー: {e_field_main}"); traceback.print_exc()
                    save_screenshot(driver, f"field_main_error_{year}_{field_name}", screenshots_dir); print(" この分野をスキップします。")
                    field_processed_successfully = False; year_processed_successfully = False
                finally:
                    if field_processed_successfully: print(f"===== 分野: {field_name} ({year}年度) 正常終了 =====")
                    else: print(f"===== 分野: {field_name} ({year}年度) 処理中断または失敗 =====")
                    # 分野完了ごと、またはエラー発生時にJSON書き込み
                    if scraped_data_all_years:
                        print(f"\n--- JSONファイル更新 ({'エラー発生時点' if not field_processed_successfully else '分野完了時点'}) ---")
                        final_data = aggregate_syllabus_data(scraped_data_all_years)
                        write_json_data(final_data, output_json_path)
                    # else: print("収集データがないためJSONは更新されません。") # ログ省略可

                field_index += 1
            # --- 分野ループ終了 ---

            if not year_processed_successfully: print(f"<<<<< {year}年度 の処理中にエラーがありましたが、次の年度へ進みます >>>>>")
            else: print(f"<<<<< {year}年度 の処理正常終了 >>>>>")
            year_index += 1
        # --- 年度ループ終了 ---

    # --- グローバル try/except/finally ---
    except KeyboardInterrupt: print("\nキーボード割り込みにより処理中断。")
    except SystemExit as e: print(f"\nスクリプト停止 (終了コード: {e.code})。")
    except Exception as e_global:
        print(f"\n★★★ 重大エラー発生、処理中断: {e_global} ★★★"); traceback.print_exc()
        if driver:
            print("重大エラー発生のため、スクリーンショットを試みます...")
            try: save_screenshot(driver, "fatal_error_global", screenshots_dir)
            except Exception as ss_err: print(f"[警告] エラー発生後のスクリーンショット保存に失敗しました: {ss_err}")
    finally:
        if driver:
            try: driver.quit(); print("\nブラウザ終了。")
            except Exception as qe: print(f"\nブラウザ終了時エラー: {qe}")

        print("\n=== 最終処理: JSONファイル書き込み ===")
        if scraped_data_all_years:
            print(f"合計 {len(scraped_data_all_years)} 件の生データ取得。")
            print("\n最終データ集約中...")
            final_json_data = aggregate_syllabus_data(scraped_data_all_years)
            if final_json_data: write_json_data(final_json_data, output_json_path)
            else: print("集約後データなし。JSON未作成。")
        else: print("\n有効データ収集されず。JSON未作成。")

        end_time = time.time()
        elapsed_time = end_time - global_start_time
        print(f"\n処理時間: {elapsed_time:.2f} 秒")
        print(f"スクレイピング終了: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
