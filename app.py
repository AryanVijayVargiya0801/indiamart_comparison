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
        clean_str = str(price_str).replace(',', '')
        match = re.search(r'(\d+(\.\d+)?)', clean_str)
        return float(match.group(1)) if match else None
    except: return None

def extract_unit(price_str):
    try:
        match = re.search(r'/\s*(\w+)', str(price_str))
        return match.group(1).strip().capitalize() if match else "Unit/Request"
    except: return "N/A"

# --- 2. THE RE-ENGINEERED SCRAPER ---
def run_scraper(query):
    # Removing the manual path to avoid the TypeError
    # We use basic headless mode with broad-spectrum bypass flags
    with SB(uc=True, headless=True, ad_block=True) as sb:
        url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        
        # Open with a generous reconnect window
        sb.uc_open_with_reconnect(url, reconnect_time=10)
        
        # Debugging: Save a screenshot if the page looks empty
        if not sb.is_element_visible('body'):
            sb.save_screenshot("empty_page.png")
            return pd.DataFrame()

        # Human-like scroll
        for _ in range(3):
            sb.execute_script("window.scrollBy(0, 800);")
            time.sleep(2)
            
        listings = []
        # Find every product container using a more general XPath
        cards = sb.find_elements('//div[contains(@class, "card")] | //div[contains(@class, "lst")] | //div[contains(@class, "item")]')
        
        for card in cards:
            try:
                # Find price using the Rupee symbol
                price_el = card.find_element('xpath', './/*[contains(text(), "₹")]')
                raw_price = price_el.text.strip()
                
                # Find product link and name
                link_el = card.find_element('xpath', './/a[contains(@href, "indiamart.com/proddetail")]')
                name = link_el.text.strip()
                link = link_el.get_attribute("href")
                
                # Seller and Location
                seller = card.find_element('xpath', './/div[contains(@class, "comp")] | .//a[contains(@class, "ls_nm")]').text
                try:
                    loc = card.find_element('xpath', './/span[contains(@class, "city")] | .//span[contains(@class, "loc")]').text
                except: loc = "India"

                listings.append({
                    "Product": name, "Price": raw_price, "Seller": seller,
                    "Location": loc, "Link": link
                })
            except: continue
            
        df = pd.DataFrame(listings).drop_duplicates()
        if not df.empty:
            df['Numeric Price'] = df['Price'].apply(clean_price)
            df['Unit'] = df['Price'].apply(extract_unit)
            # Sort by Unit and then Price
            df = df.sort_values(by=['Unit', 'Numeric Price'], ascending=[True, True])
        
        return df

# --- 3. STREAMLIT UI ---
st.set_page_config(page_title="Price Comparison", layout="wide")
st.title("📦 IndiaMart Procurement Dashboard")

with st.sidebar:
    st.header("Search")
    query_input = st.text_input("Product Name", placeholder="e.g. GI Pipes")
    search_btn = st.button("Compare Prices")

if search_btn and query_input:
    with st.status(f"Fetching data for {query_input}...", expanded=True) as status:
        data = run_scraper(query_input)
        status.update(label="Process Complete!", state="complete", expanded=False)

    if not data.empty:
        # Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Suppliers Found", len(data))
        c2.metric("Starting Price", f"₹{data['Numeric Price'].min()}")
        c3.metric("Avg Market Price", f"₹{int(data['Numeric Price'].mean())}")

        # Visualization
        st.subheader("Market Price Curve")
        data['Rank'] = range(1, len(data) + 1)
        fig = px.line(data, x="Rank", y="Numeric Price", markers=True, color="Unit",
                     hover_data=["Seller", "Location", "Product"], template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

        # Table
        st.dataframe(data[['Product', 'Numeric Price', 'Unit', 'Seller', 'Location', 'Link']],
                    column_config={"Link": st.column_config.LinkColumn("Product Link")},
                    use_container_width=True, hide_index=True)
    else:
        st.error("No data could be extracted. The site might be blocking the Cloud IP.")
