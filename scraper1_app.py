import streamlit as st
import pandas as pd
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from difflib import SequenceMatcher
import tempfile
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="B2B Marketplace Scraper",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin: 1rem 0;
    }
    .status-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.markdown('<div class="main-header">🔍 B2B Marketplace Scraper</div>', unsafe_allow_html=True)
st.markdown("**Automated trademark protection tool for Alibaba, DHgate & Made-in-China**")

# --- Sidebar Configuration ---
st.sidebar.markdown("## ⚙️ Configuration")

# File uploads
st.sidebar.markdown("### 📁 Input Files")
uploaded_csv = st.file_uploader("Upload Brand-Keywords CSV", type=['csv'], key="csv_upload")

# Site selection
st.sidebar.markdown("### 🌐 Sites to Scrape")
sites_config = {
    'Alibaba': st.sidebar.checkbox("Alibaba", value=True),
    'DHgate': st.sidebar.checkbox("DHgate", value=True),
    'Made-in-China': st.sidebar.checkbox("Made-in-China", value=True)
}

# Fuzzy matching settings
st.sidebar.markdown("### 🎯 Fuzzy Matching")
fuzzy_enabled = st.sidebar.checkbox("Enable Fuzzy Matching", value=True)
if fuzzy_enabled:
    fuzzy_threshold = st.sidebar.slider("Fuzzy Matching Threshold (%)", 70, 100, 80, 5)
else:
    fuzzy_threshold = 100

# Scraping settings
st.sidebar.markdown("### ⚡ Scraping Settings")
max_links_per_site = st.sidebar.number_input("Max Links Per Site", 1, 50, 12)
scroll_delay = st.sidebar.slider("Scroll Delay (seconds)", 1, 10, 3)
page_delay = st.sidebar.slider("Page Load Delay (seconds)", 3, 15, 5)

# Browser settings
st.sidebar.markdown("### 🖥️ Browser Settings")
headless_mode = st.sidebar.checkbox("Run in Background (Headless)", value=True)

# --- Main Content Area ---
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown('<div class="section-header">📋 Input Data Preview</div>', unsafe_allow_html=True)
    
    if uploaded_csv is not None:
        try:
            df_input = pd.read_csv(uploaded_csv)
            st.dataframe(df_input.head(), use_container_width=True)
            
            # Validate columns
            brand_col = 'Brand'
            keyword_cols = [col for col in df_input.columns if 'Keyword' in col]
            
            if brand_col not in df_input.columns:
                st.error("❌ CSV must have a 'Brand' column")
            elif not keyword_cols:
                st.error("❌ CSV must have at least one 'Keyword' column")
            else:
                st.success(f"✅ Found {len(df_input)} brands with {len(keyword_cols)} keyword columns")
                
        except Exception as e:
            st.error(f"❌ Error reading CSV: {str(e)}")
    else:
        st.info("📤 Please upload a CSV file with Brand and Keyword columns")

with col2:
    st.markdown('<div class="section-header">📊 Selected Configuration</div>', unsafe_allow_html=True)
    
    # Configuration summary
    selected_sites = [site for site, enabled in sites_config.items() if enabled]
    
    config_data = {
        "Setting": ["Sites Selected", "Fuzzy Matching", "Threshold", "Max Links/Site", "Total Expected Links*"],
        "Value": [
            f"{len(selected_sites)} sites",
            "Enabled" if fuzzy_enabled else "Disabled",
            f"{fuzzy_threshold}%" if fuzzy_enabled else "N/A",
            max_links_per_site,
            f"~{len(selected_sites) * max_links_per_site}" if uploaded_csv and selected_sites else "N/A"
        ]
    }
    
    st.dataframe(pd.DataFrame(config_data), use_container_width=True)
    st.caption("*Per brand-keyword combination")

# --- Backend Functions ---

# Fuzzy matching function
def fuzzy_match_brand(text, brand_name, threshold=80):
    if not fuzzy_enabled:
        return brand_name.lower() in text.lower()
    
    text_lower = text.lower()
    brand_lower = brand_name.lower()
    
    if brand_lower in text_lower:
        return True
    
    words = text_lower.split()
    for word in words:
        if len(word) >= 3:
            similarity = SequenceMatcher(None, brand_lower, word).ratio() * 100
            if similarity >= threshold:
                return True
    return False

# Site configurations
def get_site_configs():
    all_configs = {
        'Alibaba': {
            'url_template': 'https://www.alibaba.com/trade/search?SearchText={search_term}&page={page}',
            'url_encoding': '%20',
            'product_selector': 'a[href*="/product-detail/"]',
            'brand_in_url': True,
            'domain_check': 'alibaba.com',
            'additional_selectors': []
        },
        'DHgate': {
            'url_template': 'https://www.dhgate.com/wholesale/search.do?act=search&searchkey={search_term}&pageNum={page}',
            'url_encoding': '+',
            'product_selector': 'a[href*="/product/"]',
            'brand_in_url': False,
            'domain_check': 'dhgate.com',
            'additional_selectors': []
        },
        'Made-in-China': {
            'url_template': 'https://www.made-in-china.com/products-search/hot-china-products/{search_term}.html?page={page}',
            'url_encoding': '-',
            'product_selector': 'a[href*="/product/"]',
            'brand_in_url': False,
            'domain_check': 'made-in-china.com',
            'additional_selectors': ['a[href*="/prod/"]', '.item-link a', '.product-item a']
        }
    }
    return {k: v for k, v in all_configs.items() if sites_config.get(k, False)}

# Main scraping function - MODIFIED FOR CLOUD DEPLOYMENT
def run_scraper(df_input, progress_bar, status_text):
    results = []
    sites = get_site_configs()
    
    # Setup Chrome for Streamlit Community Cloud
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=NetworkService")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--disable-features=VizDisplayCompositor")
    
    try:
        # Use Service with no specific path; it will find the driver automatically in the cloud environment
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        st.error(f"❌ ChromeDriver Error: Could not start Chrome. Error: {str(e)}")
        return None
    
    try:
        total_operations = len(df_input) * len([col for col in df_input.columns if 'Keyword' in col]) * len(sites)
        current_operation = 0
        
        for _, row in df_input.iterrows():
            brand = row['Brand']
            keywords = [str(row[col]) for col in row.index if 'Keyword' in col and pd.notna(row[col])]
            
            for keyword in keywords:
                search_term = f"{brand} {keyword}"
                
                for site_name, config in sites.items():
                    current_operation += 1
                    progress = current_operation / total_operations
                    progress_bar.progress(progress)
                    status_text.text(f"🔍 Searching {site_name} for '{search_term}'...")
                    
                    unique_links = set()
                    page = 1
                    
                    if config['url_encoding'] == '-':
                        formatted_term = search_term.replace(' ', '-').lower()
                    else:
                        formatted_term = search_term.replace(' ', config['url_encoding'])
                    
                    search_url = config['url_template'].format(search_term=formatted_term, page=page)
                    
                    try:
                        driver.get(search_url)
                        time.sleep(page_delay)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(scroll_delay)
                        
                        links = driver.find_elements(By.CSS_SELECTOR, config['product_selector'])
                        
                        if not links and config['additional_selectors']:
                            for selector in config['additional_selectors']:
                                links.extend(driver.find_elements(By.CSS_SELECTOR, selector))
                        
                        for link in links:
                            href = link.get_attribute("href")
                            if href and config['domain_check'] in href:
                                should_add = False
                                
                                if config['brand_in_url']:
                                    should_add = fuzzy_match_brand(href, brand, fuzzy_threshold)
                                else:
                                    link_text = link.text.strip()
                                    title_attr = link.get_attribute("title") or ""
                                    alt_attr = link.get_attribute("alt") or ""
                                    combined_text = f"{link_text} {title_attr} {alt_attr}"
                                    
                                    should_add = fuzzy_match_brand(combined_text, brand, fuzzy_threshold)
                                    if not fuzzy_enabled: # If fuzzy is off, add any valid link
                                        should_add = True
                                
                                if should_add:
                                    unique_links.add(href)
                                
                                if len(unique_links) >= max_links_per_site:
                                    break
                                    
                    except Exception as e:
                        st.warning(f"⚠️ Error scraping {site_name}: {str(e)}")
                        continue
                    
                    for link in unique_links:
                        results.append({
                            "Brand": brand,
                            "Keyword": keyword,
                            "Site": site_name,
                            "Product URL": link,
                            "Scraped At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        
    finally:
        driver.quit()
    
    return pd.DataFrame(results) if results else None

# --- Execute Scraping ---
st.markdown('<div class="section-header">🚀 Execute Scraping</div>', unsafe_allow_html=True)

# The button will appear if a CSV is uploaded and at least one site is selected
if uploaded_csv is not None and selected_sites:
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button("🔥 Start Scraping", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("Initializing scraper... This may take a moment."):
                results_df = run_scraper(df_input, progress_bar, status_text)
            
            if results_df is not None and len(results_df) > 0:
                status_text.text("✅ Scraping completed!")
                
                # --- Results Section ---
                st.markdown('<div class="section-header">📊 Results Summary</div>', unsafe_allow_html=True)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total URLs", len(results_df))
                with col2:
                    st.metric("Brands Processed", results_df['Brand'].nunique())
                with col3:
                    st.metric("Sites Used", results_df['Site'].nunique())
                with col4:
                    st.metric("Keywords Used", results_df['Keyword'].nunique())
                
                site_counts = results_df['Site'].value_counts()
                st.bar_chart(site_counts)
                
                st.markdown('<div class="section-header">📋 Results Preview</div>', unsafe_allow_html=True)
                st.dataframe(results_df.head(20), use_container_width=True)
                
                # --- Download Section ---
                st.markdown('<div class="section-header">💾 Download Results</div>', unsafe_allow_html=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Excel download
                output_buffer = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
                results_df.to_excel(output_buffer.name, index=False)
                with open(output_buffer.name, 'rb') as f:
                    excel_data = f.read()
                
                st.download_button(
                    label="📊 Download Excel File",
                    data=excel_data,
                    file_name=f"b2b_scraper_results_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
                # CSV download
                csv_data = results_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 Download CSV File",
                    data=csv_data,
                    file_name=f"b2b_scraper_results_{timestamp}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                os.unlink(output_buffer.name)
                
            else:
                st.error("❌ No results found. Please check your configuration and try again.")
                
else:
    # Show missing requirements to enable the button
    missing = []
    if uploaded_csv is None:
        missing.append("📤 Upload CSV file")
    if not selected_sites:
        missing.append("🌐 Select at least one site")
    
    st.warning(f"⚠️ Please complete the configuration to start scraping: {' • '.join(missing)}")

# Footer
st.markdown("---")
st.markdown("**🛡️ Trademark Protection Tool** | Built for SDR automation and brand monitoring")