import streamlit as st
import pandas as pd
import plotly.express as px
import time
import re
from seleniumbase import SB

# --- 1. UTILITY FUNCTIONS ---
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

# --- 2. SCRAPER ENGINE ---
def run_scraper(query):
    with SB(uc=True, headless=True) as sb: 
        url = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
        sb.uc_open_with_reconnect(url, reconnect_time=4)
        
        for _ in range(3):
            sb.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)
            
        listings = []
        price_elements = sb.find_elements('//*[contains(text(), "₹")]')
        
        for p in price_elements:
            try:
                raw_price = p.text.strip()
                parent = p.find_element('xpath', './ancestor::div[contains(@class, "card") or contains(@class, "lst") or contains(@class, "item")]')
                link_el = parent.find_element('xpath', './/a[contains(@href, "indiamart.com/proddetail")]')
                
                name = link_el.text if link_el.text else "Product"
                seller = parent.find_element('xpath', './/div[contains(@class, "comp") or contains(@class, "ls_nm")]').text
                
                try:
                    location = parent.find_element('xpath', './/span[contains(@class, "city") or contains(@class, "loc")]').text
                except: location = "Not Specified"
                
                listings.append({
                    "Product": name.strip(),
                    "Price": raw_price,
                    "Seller": seller.strip(),
                    "Location": location.strip(),
                    "Link": link_el.get_attribute("href")
                })
            except: continue
            
        df = pd.DataFrame(listings).drop_duplicates()
        if not df.empty:
            df['Numeric Price'] = df['Price'].apply(clean_price)
            df['Unit'] = df['Price'].apply(extract_unit)
            # Important: Sort by unit then price for the chart to look right
            df = df.sort_values(by=['Unit', 'Numeric Price'], ascending=[True, True])
        return df

# --- 3. STREAMLIT UI ---
st.set_page_config(page_title="Price Comparison Dashboard", layout="wide")
st.title("📦 Product Comparison Dashboard")

with st.sidebar:
    st.header("Search Parameters")
    search_query = st.text_input("Enter Product Name:", placeholder="e.g. Industrial Valves")
    search_button = st.button("Run Comparison")

if search_button and search_query:
    with st.status(f"Fetching data for '{search_query}'...", expanded=True) as status:
        data = run_scraper(search_query)
        status.update(label="Data Retrieval Complete!", state="complete", expanded=False)

    if not data.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Sellers Analyzed", len(data))
        col2.metric("Minimum Price", f"₹{data['Numeric Price'].min()}")
        col3.metric("Max Price", f"₹{data['Numeric Price'].max()}")

        # --- NEW VISUALIZATION SECTION ---
        st.subheader("Price Trends across Sellers")
        
        # Add a rank column for the X-axis
        data['Rank'] = range(1, len(data) + 1)
        
        # Create Line Chart with Markers (Dots)
        fig = px.line(
            data, 
            x="Rank", 
            y="Numeric Price", 
            color="Unit", # Different lines for different units (Kg vs Piece)
            markers=True, # Adds the dots for each seller
            title="Seller Price Curve (Cheapest to Most Expensive)",
            labels={"Rank": "Seller Rank (Cheapest First)", "Numeric Price": "Price (INR)"},
            hover_data=["Seller", "Product", "Location"], # Show details on hover
            template="plotly_white"
        )
        # Make the lines a bit smoother
        fig.update_traces(line_shape='spline')
        st.plotly_chart(fig, use_container_width=True)
        # ---------------------------------

        # Data Table
        st.subheader("Supplier Details")
        st.dataframe(
            data[['Product', 'Numeric Price', 'Unit', 'Seller', 'Location', 'Link']],
            column_config={"Link": st.column_config.LinkColumn("Product Link")},
            use_container_width=True, hide_index=True
        )
    else:
        st.error("No data found. Please refine the search term.")
