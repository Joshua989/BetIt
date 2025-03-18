from flask import Flask, render_template, request, jsonify
import requests, json, time, re, os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

app = Flask(__name__)

def get_sportybet_events(booking_code):
    url = f"https://www.sportybet.com/api/ng/orders/share/{booking_code}?_t={int(time.time()*1000)}"
    headers = {"Accept":"application/json, text/plain, */*", "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "clientId":"web", "operid":"3", "platform":"web"}
    try:
        response = requests.get(url, headers=headers, timeout=15, verify=True)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def force_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        try:
            webdriver.ActionChains(driver).move_to_element(element).click().perform()
            return True
        except:
            return False

def find_match_element(driver, home_team, away_team):
    try:
        all_matches = driver.find_elements(By.CSS_SELECTOR, ".match-content__row--team")
        best_match, highest_score = None, 0
        for i in range(0, len(all_matches)-1, 2):
            if i+1 >= len(all_matches): break
            team1, team2 = all_matches[i].text.strip(), all_matches[i+1].text.strip()
            score1, score2 = team_similarity_score(team1, home_team), team_similarity_score(team2, away_team)
            total_score = score1 + score2
            if total_score > highest_score: highest_score, best_match = total_score, (all_matches[i], all_matches[i+1])
        return best_match if best_match and highest_score >= 140 else None
    except:
        return None

def team_similarity_score(team1, team2):
    team1, team2 = team1.lower().strip(), team2.lower().strip()
    if team1 == team2: return 100
    if team1 in team2 or team2 in team1: return 80
    replacements = {"united":"utd", "fc":"", "f.c.":"", "city":""}
    normalized1, normalized2 = team1, team2
    for old, new in replacements.items():
        normalized1, normalized2 = normalized1.replace(old, new), normalized2.replace(old, new)
    normalized1, normalized2 = " ".join(normalized1.split()), " ".join(normalized2.split())
    if normalized1 == normalized2: return 90
    if normalized1 in normalized2 or normalized2 in normalized1: return 70
    words1, words2 = normalized1.split(), normalized2.split()
    common_words = sum(1 for w in words1 if any(w in x for x in words2))
    return common_words*20 if common_words > 0 else 0

def select_market_option(driver, match_element, market_type, selection_desc):
    try:
        match_container = match_element[0].find_element(By.XPATH, "ancestor::div[contains(@class,'match-content')]")
        odds_container = match_container.find_element(By.XPATH, "following-sibling::div[contains(@class,'bets')]")
        odds_links = odds_container.find_elements(By.CSS_SELECTOR, ".bets_item--link") or odds_container.find_elements(By.CSS_SELECTOR, "a[href='javascript:;']")
        if odds_links:
            odds_index = 0
            market_type, selection_desc = market_type.lower(), selection_desc.lower()
            if "1x2" in market_type or "match result" in market_type:
                if "1" in selection_desc or "home" in selection_desc: odds_index = 0
                elif "x" in selection_desc or "draw" in selection_desc: odds_index = 1
                elif "2" in selection_desc or "away" in selection_desc: odds_index = 2
            elif "over/under" in market_type:
                odds_index = 0 if "over" in selection_desc else 1
            elif "gg" in market_type or "goal" in market_type:
                odds_index = 0 if "yes" in selection_desc else 1
            return force_click(driver, odds_links[odds_index if odds_index<len(odds_links) else 0])
        return False
    except:
        return False

def try_advanced_selection(driver, match_element):
    try:
        match_row = match_element[0].find_element(By.XPATH, "ancestor::div[contains(@class,'table-a')]")
        odds_elements = match_row.find_elements(By.CSS_SELECTOR, "a[href='javascript:;']")
        filtered_odds = [odd for odd in odds_elements if odd.is_displayed() and odd.text.strip() and odd.text.strip()[0].isdigit()]
        return force_click(driver, filtered_odds[0]) if filtered_odds else False
    except:
        return False

def try_clicking_any_odds(driver):
    try:
        odds_links = driver.find_elements(By.CSS_SELECTOR, "a.bets_item--link")
        for link in odds_links:
            if link.is_displayed(): return force_click(driver, link)
        return False
    except:
        return False   

def click_book_a_bet_button(driver):
    try:
        book_button = driver.find_element(By.ID, "bookABetButton")
        return force_click(driver, book_button)
    except:
        try:
            book_button = driver.find_element(By.XPATH, "//button[contains(text(),'Book a bet')]")
            return force_click(driver, book_button)
        except:
            try:
                driver.execute_script("document.getElementById('bookABetButton').click();")
                return True
            except:
                return False

def book_bet_on_bet9ja(data, stake_amount=100):
    try:
        outcomes = data.get('data', {}).get('outcomes', []) or data.get('data', {}).get('events', [])
        if not outcomes: return None
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
        service = Service(os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver"))
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"""})
        try:
            driver.set_script_timeout(30)
            driver.get("https://sports.bet9ja.com/")
            time.sleep(5)
            if "Please confirm you are over 18" in driver.page_source:
                driver.execute_script("var btn=document.querySelector('button.btn-primary');if(btn){btn.click();}")
                time.sleep(2)
            successful_selections = []
            for outcome in outcomes[:3]:
                home_team = outcome.get('homeTeamName', outcome.get('homeTeam', outcome.get('home', '')))
                away_team = outcome.get('awayTeamName', outcome.get('awayTeam', outcome.get('away', '')))
                markets = outcome.get('markets', [])
                if not markets: continue
                market = markets[0]
                market_type = market.get('desc', '')
                selections = market.get('outcomes', [])
                if not selections: continue
                selection = selections[0]
                selection_desc = selection.get('desc', '')
                for page in ["today", "tomorrow", "upcoming"]:
                    driver.get(f"https://sports.bet9ja.com/mobile/dailybundle/soccer/{page}")
                    time.sleep(5)
                    try:
                        search_box = driver.find_element(By.CSS_SELECTOR, "input.form-control,input.search-input,input[type='search']")
                        search_box.clear()
                        search_box.send_keys(f"{home_team}")
                        try:
                            search_button = driver.find_element(By.CSS_SELECTOR, "button.search-button,button[type='submit']")
                            search_button.click()
                        except:
                            driver.execute_script("document.querySelector('input.search-input').dispatchEvent(new KeyboardEvent('keydown',{'key':'Enter'}));")
                        time.sleep(3)
                    except: pass
                    match_element = find_match_element(driver, home_team, away_team)
                    if match_element:
                        selected = select_market_option(driver, match_element, market_type, selection_desc) or try_advanced_selection(driver, match_element)
                        if selected:
                            successful_selections.append({'match': f"{match_element[0].text.strip()} vs {match_element[1].text.strip()}"})
                            break
                if len(successful_selections) >= 2: break
            if len(successful_selections) < 2:
                for _ in range(3):
                    driver.get("https://sports.bet9ja.com/mobile/dailybundle/soccer/today")
                    time.sleep(5)
                    if try_clicking_any_odds(driver):
                        successful_selections.append({'match': "Random match"})
                    if len(successful_selections) >= 2: break
            if successful_selections:
                time.sleep(3)
                driver.get("https://sports.bet9ja.com/mobile/betslip")
                time.sleep(5)
                stake_script = """var inputs=document.querySelectorAll('input[type="number"],input.stake-input,[class*="stake"]');for(var i=0;i<inputs.length;i++){if(inputs[i].offsetParent!==null){inputs[i].value='"""+str(int(stake_amount))+"""';inputs[i].dispatchEvent(new Event('input',{bubbles:true}));inputs[i].dispatchEvent(new Event('change',{bubbles:true}));return true;}}return false;"""
                driver.execute_script(stake_script)
                time.sleep(2)
                click_book_a_bet_button(driver) or driver.execute_script("""var bookButton=document.getElementById('bookABetButton');if(bookButton){bookButton.click();return true;}bookButton=document.querySelector('button.btn-gray');if(bookButton){bookButton.click();return true;}var buttons=document.querySelectorAll('button');for(var i=0;i<buttons.length;i++){if(buttons[i].textContent.includes('Book a bet')){buttons[i].click();return true;}}return false;""")
                time.sleep(8)
                try:
                    page_source = driver.page_source
                    booking_pattern = re.compile(r"(?:Booking Number|Code|Reference):?\s*([A-Z0-9]{6,})")
                    match = booking_pattern.search(page_source)
                    if match:
                        booking_code = match.group(1)
                        return booking_code
                    else:
                        code_elements = driver.find_elements(By.XPATH, "//*[contains(text(),'Booking') or contains(text(),'Code') or contains(text(),'Reference')]")
                        for elem in code_elements:
                            elem_text = elem.text
                            if elem_text:
                                code_match = re.search(r"([A-Z0-9]{6,})", elem_text)
                                if code_match:
                                    return code_match.group(1)
                        all_elements = driver.find_elements(By.XPATH, "//*")
                        for elem in all_elements:
                            try:
                                elem_text = elem.text
                                if elem_text and re.match(r"^[A-Z0-9]{6,}$", elem_text.strip()):
                                    return elem_text.strip()
                            except: pass
                        return "UNKNOWN"
                except:
                    return None
            else: return None
        finally:
            driver.quit()
    except: return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    booking_code = request.form.get('booking_code')
    stake_amount = float(request.form.get('stake_amount', 100))
    data = get_sportybet_events(booking_code)
    if not data:
        return jsonify({"result": "Failed to retrieve booking details"})
    bet9ja_booking_code = book_bet_on_bet9ja(data, stake_amount)
    if bet9ja_booking_code:
        return jsonify({"result": f"Booking Code: {bet9ja_booking_code}"})
    else:
        return jsonify({"result": "Failed to book on Bet9ja"})

if __name__ == "__main__":
    app.run(debug=True)