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
    # We use basic headless mode but add 'stealth' flags manually 
    # to avoid the PermissionError triggered by uc=True
    with SB(headless=True, browser="chrome") as sb:
        
        # Manually apply stealth settings to mimic a real browser
        sb.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            """
        })

        url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        sb.open(url)
        
        # Give it a moment to settle
        time.sleep(5)
        
        # Human-like scrolling
        for _ in range(3):
            sb.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)
            
        listings = []
        # Finding elements that contain the Rupee symbol
        price_elements = sb.find_elements('//*[contains(text(), "₹")]')
        
        for p in price_elements:
            try:
                raw_price = p.text.strip()
                if not raw_price or len(raw_price) > 30: continue
                
                # Navigate to the product card
                parent = p.find_element('xpath', './ancestor::div[contains(@class, "card") or contains(@class, "lst") or contains(@class, "item")]')
                
                # Robust extraction
                name_els = parent.find_elements('xpath', './/h2 | .//span[contains(@class, "nm")] | .//a[contains(@href, "proddetail")]')
                name = name_els[0].text if name_els else "Product"
                
                link_els = parent.find_elements('xpath', './/a[contains(@href, "indiamart.com/proddetail")]')
                link = link_els[0].get_attribute("href") if link_els else "#"
                
                seller_els = parent.find_elements('xpath', './/div[contains(@class, "comp")] | .//a[contains(@class, "ls_nm")]')
                seller = seller_els[0].text if seller_els else "Unknown Seller"
                
                try:
                    loc = parent.find_element('xpath', './/span[contains(@class, "city")] | .//span[contains(@class, "loc")]').text
                except: loc = "India"
                
                listings.append({
                    "Product": name.strip(),
                    "Price": raw_price,
                    "Seller": seller.strip(),
                    "Location": loc.strip(),
                    "Link": link
                })
            except: continue
            
        df = pd.DataFrame(listings).drop_duplicates()
        if not df.empty:
            df['Numeric Price'] = df['Price'].apply(clean_price)
            df['Unit'] = df['Price'].apply(extract_unit)
            df = df.sort_values(by=['Unit', 'Numeric Price'], ascending=[True, True])
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
