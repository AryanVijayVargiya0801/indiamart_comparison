import streamlit as st
import pandas as pd
import plotly.express as px
import time
import re
import random
from seleniumbase import SB

# --- 1. CLEANING FUNCTIONS ---
def clean_price(price_str):
    if not price_str: return None
    try:
        clean_str = str(price_str).replace(',', '')
        match = re.search(r'(\d+(\.\d+)?)', clean_str)
        return float(match.group(1)) if match else None
    except: return None

def extract_unit(price_str):
    if not price_str: return "N/A"
    try:
        match = re.search(r'/\s*(\w+)', str(price_str))
        return match.group(1).strip().capitalize() if match else "Unit/Request"
    except: return "N/A"

# --- 2. THE STABLE CLOUD SCRAPER ---
def run_scraper(query):
    # We remove 'driver_executable_path' to fix the TypeError.
    # 'uc=True' and 'headless=True' are the essential flags for Streamlit Cloud.
    with SB(uc=True, headless=True, ad_block=True) as sb:
        
        url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        
        # Streamlit Cloud needs a slightly longer reconnect time to bypass the "Bot Check"
        sb.uc_open_with_reconnect(url, reconnect_time=10)
        
        # Human-like interaction: Scroll 3 times with random pauses
        for _ in range(3):
            sb.execute_script(f"window.scrollBy(0, {random.randint(600, 900)});")
            time.sleep(random.uniform(1.5, 3.0))
            
        listings = []
        # Finding elements that contain the Rupee symbol
        price_elements = sb.find_elements('//*[contains(text(), "₹")]')
        
        for p in price_elements:
            try:
                raw_price = p.text.strip()
                if not raw_price or len(raw_price) > 30: continue
                
                # Navigate to the card container
                parent = p.find_element('xpath', './ancestor::div[contains(@class, "card") or contains(@class, "lst") or contains(@class, "item")]')
                
                # Extract details with plural 'find_elements' to avoid crashes
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

# --- 3. STREAMLIT UI ---
st.set_page_config(page_title="Price Comparison Dashboard", layout="wide")
st.title("📦 IndiaMart Procurement Dashboard")

with st.sidebar:
    st.header("Search Parameters")
    search_query = st.text_input("Enter Product Name:", placeholder="e.g. Industrial Valves")
    search_button = st.button("Run Comparison")

if search_button and search_query:
    with st.status(f"Scanning market for '{search_query}'...", expanded=True) as status:
        data = run_scraper(search_query)
        status.update(label="Scanning Complete!", state="complete", expanded=False)

    if not data.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Suppliers Found", len(data))
        col2.metric("Minimum Price", f"₹{data['Numeric Price'].min():,.0f}")
        col3.metric("Avg Market Rate", f"₹{int(data['Numeric Price'].mean()):,.0f}")

        # Visualization
        st.subheader("Market Price Curve")
        data['Rank'] = range(1, len(data) + 1)
        fig = px.line(data, x="Rank", y="Numeric Price", color="Unit", markers=True, 
                     title="Seller Price Curve", template="plotly_white", line_shape="spline",
                     hover_data=["Seller", "Location", "Product"])
        st.plotly_chart(fig, use_container_width=True)

        # Table
        st.dataframe(data[['Product', 'Numeric Price', 'Unit', 'Seller', 'Location', 'Link']],
                    column_config={"Link": st.column_config.LinkColumn("Product Link")},
                    use_container_width=True, hide_index=True)
    else:
        st.error("No data found. If this persists, the Cloud IP might be temporarily blocked.")
