import streamlit as st
import pandas as pd
import plotly.express as px
import time
import re
import random
from seleniumbase import SB

# --- 1. SMART UTILITY FUNCTIONS ---
def clean_price(price_str):
    """Turns messy text like '₹ 1,500/Piece' into 1500.0"""
    if not price_str:
        return None
    try:
        clean_str = price_str.replace(',', '').replace('₹', '').strip()
        match = re.search(r'(\d+(\.\d+)?)', clean_str)
        return float(match.group(1)) if match else None
    except Exception:
        return None

def extract_unit(price_str):
    """Categorizes products by how they are sold (Kg, Piece, Meter)."""
    if not price_str:
        return "Price on Request"
    try:
        match = re.search(r'/\s*(\w+)', price_str)
        return match.group(1).strip().capitalize() if match else "Unit/Request"
    except Exception:
        return "N/A"

# --- 2. RESILIENT SCRAPER ENGINE ---
def run_scraper(query):
    with SB(headless=True, browser="chrome") as sb:
        # Manual stealth to avoid blocks
        sb.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """
        })

        url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        sb.open(url)
        
        # --- THE FIX: WAIT FOR CONTENT ---
        # We wait up to 15 seconds for a price symbol to appear on the page
        try:
            sb.wait_for_element('//*[contains(text(), "₹")]', timeout=15)
        except:
            return pd.DataFrame() # Return empty if page never loads

        # Scroll slowly to trigger lazy-load
        for _ in range(3):
            sb.execute_script("window.scrollBy(0, 800);")
            time.sleep(2)
            
        listings = []
        # Find every 'card-like' div. IndiaMart uses many different classes, 
        # so we look for common patterns in the ID or class.
        cards = sb.find_elements('//div[contains(@id, "lst")] | //div[contains(@class, "card")] | //div[contains(@class, "item")]')
        
        for card in cards:
            try:
                # Try to find a price inside this specific card
                price_el = card.find_element('xpath', './/*[contains(text(), "₹")]')
                raw_price = price_el.text.strip()
                
                # Try to find a link (the product title)
                link_el = card.find_element('xpath', './/a[contains(@href, "proddetail")]')
                name = link_el.text.strip()
                link = link_el.get_attribute("href")
                
                # Seller and Location
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
        # ... (cleaning logic remains same) ...
        return df
# --- 3. THE "HUMAN" DASHBOARD UI ---
st.set_page_config(page_title="Market Insights", page_icon="📈", layout="wide")

st.title("🚜 Smart Procurement Assistant")
st.markdown(f"Helping you find the best market rates since {time.strftime('%Y')}")

# Sidebar setup
with st.sidebar:
    st.header("What are we looking for?")
    search_query = st.text_input("Product Search", placeholder="e.g. HDPE Pipes")
    search_button = st.button("Analyze Market")
    st.divider()
    st.info("Tip: This tool groups products by 'Unit' (Kg vs Piece) to ensure you compare apples to apples.")

if search_button and search_query:
    with st.status(f"Scanning IndiaMart for '{search_query}'...", expanded=True) as status:
        market_data = run_scraper(search_query)
        if not market_data.empty:
            status.update(label="Analysis Complete!", state="complete", expanded=False)
        else:
            status.update(label="No Data Found.", state="error")

    if not market_data.empty:
        # Key Performance Indicators
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Suppliers Found", len(market_data))
        kpi2.metric("Starting Price", f"₹{market_data['Numeric Price'].min():,.0f}")
        kpi3.metric("Avg Market Price", f"₹{market_data['Numeric Price'].mean():,.0f}")

        # Visualization
        st.subheader("📊 The Price Curve")
        market_data['Seller Rank'] = range(1, len(market_data) + 1)
        
        fig = px.line(
            market_data, 
            x="Seller Rank", 
            y="Numeric Price", 
            color="Unit",
            markers=True,
            title=f"Price Distribution for {search_query}",
            hover_data=["Seller", "Location", "Product"],
            template="plotly_white",
            line_shape="spline"
        )
        st.plotly_chart(fig, use_container_width=True)

        # Interactive Table
        st.subheader("🔍 Verified Seller List")
        
        # Search/Filter inside the results
        col_search, col_city = st.columns([2, 1])
        with col_city:
            cities = ["All Cities"] + sorted(market_data['Location'].unique().tolist())
            city_filter = st.selectbox("Location Filter", cities)
            
        final_view = market_data if city_filter == "All Cities" else market_data[market_data['Location'] == city_filter]

        st.dataframe(
            final_view[['Product', 'Numeric Price', 'Unit', 'Seller', 'Location', 'Link']],
            column_config={
                "Numeric Price": st.column_config.NumberColumn("Rate (₹)", format="₹%d"),
                "Link": st.column_config.LinkColumn("View on IndiaMart")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Download Data
        st.download_button(
            "📥 Export Market Report (CSV)",
            data=final_view.to_csv(index=False).encode('utf-8'),
            file_name=f"market_report_{search_query}.csv",
            mime="text/csv"
        )
    else:
        st.warning("I couldn't find any listings for that. Try a broader search term (e.g., 'Steel' instead of 'Grade 304 Steel').")
