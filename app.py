import streamlit as st
import pandas as pd
import plotly.express as px
import time
import re
import os
from seleniumbase import SB

# --- 1. CLEANING FUNCTIONS ---
def clean_price(price_str):
    try:
        clean_str = price_str.replace(',', '')
        match = re.search(r'(\d+(\.\d+)?)', clean_str)
        return float(match.group(1)) if match else None
    except: return None

def extract_unit(price_str):
    try:
        match = re.search(r'/\s*(\w+)', price_str)
        return match.group(1).strip().capitalize() if match else "Unit/Request"
    except: return "N/A"

# --- 2. THE DEBUGGING SCRAPER ---
def run_scraper(query):
    # Use a specific directory for screenshots in the cloud
    screenshot_path = "error_screenshot.png"
    
    with SB(uc=True, headless=True, ad_block=True, driver_executable_path="/tmp/chromedriver") as sb:
        url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        
        # 1. Open with a longer timeout
        sb.uc_open_with_reconnect(url, reconnect_time=8)
        
        # 2. Wait for the core search results container
        try:
            # Look for ANY price symbol to confirm page is loaded
            sb.wait_for_element('//*[contains(text(), "₹")]', timeout=15)
        except Exception:
            # CAPTURE SCREENSHOT IF IT FAILS
            sb.save_screenshot(screenshot_path)
            return pd.DataFrame(), screenshot_path

        # 3. Scroll to load lazy-load items
        for _ in range(3):
            sb.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)
            
        # 4. Extract data using broad patterns
        listings = []
        # Target the product cards
        cards = sb.find_elements('//div[contains(@class, "card")] | //div[contains(@class, "lst")] | //li[contains(@class, "item")]')
        
        for card in cards:
            try:
                price_el = card.find_element('xpath', './/*[contains(text(), "₹")]')
                raw_price = price_el.text.strip()
                
                # Title and Link
                link_el = card.find_element('xpath', './/a[contains(@href, "proddetail")] | .//h2/a')
                name = link_el.text.strip()
                link = link_el.get_attribute("href")
                
                # Seller & Location
                seller = card.find_element('xpath', './/div[contains(@class, "comp")] | .//a[contains(@class, "ls_nm")]').text
                try:
                    loc = card.find_element('xpath', './/span[contains(@class, "city")] | .//span[contains(@class, "loc")]').text
                except:
                    loc = "India"

                listings.append({
                    "Product": name, "Price": raw_price, "Seller": seller,
                    "Location": loc, "Link": link
                })
            except:
                continue
            
        df = pd.DataFrame(listings).drop_duplicates()
        if not df.empty:
            df['Numeric Price'] = df['Price'].apply(clean_price)
            df['Unit'] = df['Price'].apply(extract_unit)
            df = df.sort_values(by=['Unit', 'Numeric Price'], ascending=[True, True])
            
        return df, None

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="IndiaMart Procurement", layout="wide")
st.title("📦 Smart Sourcing Dashboard")

with st.sidebar:
    query_input = st.text_input("What are you looking for?", placeholder="e.g. PVC Fittings")
    start_btn = st.button("Search Market")

if start_btn and query_input:
    with st.status("Analyzing Market Data...", expanded=True) as status:
        results, error_img = run_scraper(query_input)
        
        if not results.empty:
            status.update(label="Analysis Complete!", state="complete")
            
            # KPI Metrics
            m1, m2, m3 = st.columns(3)
            m1.metric("Suppliers", len(results))
            m2.metric("Min Rate", f"₹{results['Numeric Price'].min()}")
            m3.metric("Max Rate", f"₹{results['Numeric Price'].max()}")
            
            # Plot
            results['Rank'] = range(1, len(results) + 1)
            fig = px.line(results, x="Rank", y="Numeric Price", markers=True, color="Unit",
                         hover_data=["Seller", "Location"], title="Market Price Distribution")
            st.plotly_chart(fig, use_container_width=True)
            
            # Table
            st.dataframe(results[['Product', 'Numeric Price', 'Unit', 'Seller', 'Location', 'Link']],
                        column_config={"Link": st.column_config.LinkColumn("Product Link")},
                        use_container_width=True, hide_index=True)
        else:
            status.update(label="Extraction Failed", state="error")
            st.error("I couldn't find any products. This usually means the site is blocking the request.")
            
            if error_img and os.path.exists(error_img):
                st.subheader("Debug View: What the bot sees")
                st.image(error_img, caption="If this shows a CAPTCHA, the Cloud IP is blocked.")
