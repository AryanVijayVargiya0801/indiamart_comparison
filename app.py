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
    # 'uc=True' is our stealth mode
    with SB(uc=True, headless=True, ad_block=True, driver_executable_path="/tmp/chromedriver") as sb:
        
        # Mimic a real person's browser signature
        sb.driver.execute_cdp_cmd("Network.setUserAgentOverride", {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        })
        
        search_url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        sb.uc_open_with_reconnect(search_url, reconnect_time=7)
        
        # Human-like scrolling behavior
        for _ in range(random.randint(3, 5)):
            sb.execute_script(f"window.scrollBy(0, {random.randint(700, 1100)});")
            time.sleep(random.uniform(1.0, 2.5))
            
        listings = []
        # Finding elements that look like price tags
        price_tags = sb.find_elements('//*[contains(text(), "₹")]')
        
        for p in price_tags:
            try:
                raw_price = p.text.strip()
                if not raw_price or len(raw_price) > 25: # Filter out noise
                    continue
                
                # Pivot to the parent container to get full product context
                container = p.find_element('xpath', './ancestor::div[contains(@class, "card") or contains(@class, "lst") or contains(@class, "item")]')
                
                # Extracting details with fallback names
                name_el = container.find_elements('xpath', './/a[contains(@href, "proddetail")] | .//h2 | .//span[contains(@class, "nm")]')
                product_name = name_el[0].text.strip() if name_el else "Unknown Product"
                
                link_el = container.find_elements('xpath', './/a[contains(@href, "indiamart.com/proddetail")]')
                product_link = link_el[0].get_attribute("href") if link_el else "#"
                
                seller_el = container.find_elements('xpath', './/div[contains(@class, "comp")] | .//a[contains(@class, "ls_nm")]')
                seller_name = seller_el[0].text.strip() if seller_el else "Contact Seller"
                
                loc_el = container.find_elements('xpath', './/span[contains(@class, "city")] | .//span[contains(@class, "loc")]')
                location = loc_el[0].text.strip() if loc_el else "India"

                listings.append({
                    "Product": product_name,
                    "Price": raw_price,
                    "Seller": seller_name,
                    "Location": location,
                    "Link": product_link
                })
            except Exception:
                continue
            
        df = pd.DataFrame(listings).drop_duplicates(subset=['Product', 'Seller'])
        
        if not df.empty:
            df['Numeric Price'] = df['Price'].apply(clean_price)
            df['Unit'] = df['Price'].apply(extract_unit)
            # Sort for better comparison logic
            df = df.sort_values(by=['Unit', 'Numeric Price'], ascending=[True, True]).reset_index(drop=True)
            
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
