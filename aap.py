import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
from fpdf import FPDF
from datetime import datetime

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="StockValue AI", page_icon="📈", layout="wide")

st.markdown("""
<style>
    /* Clean UI Overrides */
    .stApp { background-color: #0E1117; }
    
    /* BIG VERDICT BANNERS */
    .verdict-box {
        padding: 20px; 
        border-radius: 12px; 
        color: white; 
        text-align: center; 
        margin-bottom: 20px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.15);
        font-family: 'Arial', sans-serif;
    }
    .verdict-green { background: linear-gradient(135deg, #28a745, #20c997); }
    .verdict-red { background: linear-gradient(135deg, #dc3545, #ff6b6b); }
    .verdict-neutral { background: linear-gradient(135deg, #304352, #d7d2cc); }
    
    .verdict-title { font-size: 28px; font-weight: 800; margin: 0; letter-spacing: 1px;}
    .verdict-sub { font-size: 18px; margin-top: 5px; opacity: 0.95; font-weight: 500;}
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 2. BACKEND FUNCTIONS ---

@st.cache_data(ttl=3600*24)
def search_ticker(query):
    """Finds the best ticker from a search query using Yahoo's hidden API."""
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5).json()
        if 'quotes' in response and len(response['quotes']) > 0:
            return response['quotes'][0]['symbol']
    except Exception:
        pass
    return None

@st.cache_data(ttl=900)
def get_stock_data(ticker):
    """
    Robust Data Fetcher: Tries 3 methods to avoid API blocks.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # LAYER 1: GET PRICE (Critical)
        current_price = 0.0
        try:
            current_price = stock.fast_info['last_price']
        except:
            try:
                hist = stock.history(period="1d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                else:
                    return None
            except:
                return None

        # LAYER 2: GET INFO (Metadata)
        info = {}
        try:
            info = stock.info
        except:
            pass 

        # Defaults if API partially fails
        currency = "₹" if info.get('currency') == "INR" else "$"
        name = info.get('shortName', ticker)
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        
        # Valuation Logic
        negative_earnings = eps < 0
        graham_num = 0
        if eps > 0 and bvps > 0:
            graham_num = (22.5 * eps * bvps) ** 0.5 

        # LAYER 3: HISTORY & AI TREND PREDICTION
        trend_direction = "Neutral"
        ai_price_target = 0
        history = pd.DataFrame() # Default empty
        
        try:
            # We fetch history HERE so we can save the data, not the object
            history = stock.history(period="1y")
            
            if not history.empty:
                # Calculate AI Trend
                history_ai = history.reset_index()
                # --- THIS WAS THE LINE THAT BROKE BEFORE ---
                history_ai['DateOrdinal'] = pd.to_datetime(history_ai['Date']).map(pd.Timestamp.toordinal)
                
                X = history_ai[['DateOrdinal']].values
                y = history_ai['Close'].values
                model = LinearRegression()
                model.fit(X, y)
                future_ordinal = X[-1][0] + 30
                ai_price_target = model.predict([[future_ordinal]])[0]
                trend_direction = "Bullish" if ai_price_target > current_price else "Bearish"
        except:
            pass 

        return {
            "symbol": ticker, "name": name, "currency": currency, "price": current_price,
            "change": current_price - info.get('previousClose', current_price),
            "market_cap": info.get('marketCap', 0), "pe": info.get('trailingPE', 0),
            "high_52": info.get('fiftyTwoWeekHigh', 0), "low_52": info.get('fiftyTwoWeekLow', 0),
            "eps": eps, "bvps": bvps, "div_yield": info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0,
            "sector": info.get('sector', 'Unknown'), "graham_num": graham_num,
            "negative_earnings": negative_earnings, "ai_trend": trend_direction,
            "ai_price": ai_price_target, "analyst_target": info.get('targetMeanPrice', 0),
            "analyst_rec": info.get('recommendationKey', 'N/A').replace('_', ' ').title(),
            "history": history # <--- Saving the DATA, not the object (Fixes Cache Error)
        }
    except Exception:
        return None

def create_pdf(data):
    """Generates a PDF report."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Investment Report: {data['name']}", ln=True, align='C')
    pdf.ln(10)
    pdf.cell(0, 10, txt=f"Price: {data['currency']}{data['price']:.2f}", ln=True)
    
    if data['negative_earnings']:
        pdf.set_text_color(220, 50, 50)
        pdf.cell(0, 10, txt="WARNING: Negative Earnings. Graham Value N/A.", ln=True)
        pdf.set_text_color(0, 0, 0)
    elif data['graham_num'] > 0:
        pdf.cell(0, 10, txt=f"Fair Value: {data['currency']}{data['graham_num']:.2f}", ln=True)
        
    pdf.ln(10)
    pdf.cell(0, 10, txt="Generated by StockValue AI", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- 3. MAIN APP UI ---
st.title("📈 StockValue AI")
st.write("Smart Intrinsic Value Calculator (US & India)")

# Search Bar
col_search, col_space = st.columns([3, 1])
with col_search:
    search_query = st.text_input("Search Stock", placeholder="e.g. Zomato, Nvidia, Tata Motors", label_visibility="collapsed")

ticker = None
if search_query:
    if len(search_query) < 6 and search_query.isalpha():
         ticker = search_query.upper()
         if ticker in ["RELIANCE", "TATASTEEL", "HDFCBANK", "INFY", "ITC", "SBIN"]:
             ticker += ".NS"
    else:
        with st.spinner(f"Searching for '{search_query}'..."):
            ticker = search_ticker(search_query)

if ticker:
    data = get_stock_data(ticker)
    
    if data:
        # A. HEADER
        st.markdown("---")
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        with c1:
            st.markdown(f"### {data['name']} ({data['symbol']})")
            color = "green" if data['change'] >= 0 else "red"
            st.markdown(f"**{data['currency']}{data['price']:.2f}** <span style='color:{color};'> {data['change']:+.2f}</span>", unsafe_allow_html=True)
        with c2: st.metric("Market Cap", f"{data['currency']}{data['market_cap'] / 1e9:,.1f}B")
        with c3: st.metric("P/E Ratio", f"{data['pe']:.2f}" if data['pe'] else "N/A")
        with c4:
            try:
                pdf_bytes = create_pdf(data)
                st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"{data['symbol']}_Report.pdf", mime='application/pdf')
            except: st.warning("PDF N/A")

        # B. THE BIG VERDICT
        st.markdown("<br>", unsafe_allow_html=True)
        if data['negative_earnings']:
             st.markdown(f"""
            <div class="verdict-box verdict-neutral">
                <p class="verdict-title">⚠️ NEGATIVE EARNINGS</p>
                <p class="verdict-sub">Company is loss-making (EPS: {data['eps']}). Valuation models do not apply.</p>
            </div>
            """, unsafe_allow_html=True)
        elif data['graham_num'] > 0:
            diff = ((data['graham_num'] - data['price']) / data['price']) * 100
            if diff > 10:
                st.markdown(f"""
                <div class="verdict-box verdict-green">
                    <p class="verdict-title">✅ UNDERVALUED</p>
                    <p class="verdict-sub">Trading {diff:.1f}% BELOW Fair Value</p>
                </div>""", unsafe_allow_html=True)
            elif diff < -10:
                st.markdown(f"""
                <div class="verdict-box verdict-red">
                    <p class="verdict-title">❌ OVERVALUED</p>
                    <p class="verdict-sub">Trading {abs(diff):.1f}% ABOVE Fair Value</p>
                </div>""", unsafe_allow_html=True)
            else:
                 st.markdown(f"""
                <div class="verdict-box verdict-neutral">
                    <p class="verdict-title">⚖️ FAIRLY VALUED</p>
                    <p class="verdict-sub">Trading within fair range.</p>
                </div>""", unsafe_allow_html=True)

        # C. INTERACTIVE CHART
        st.subheader("📊 Price Action")
        # We now use the saved data, NOT the object
        hist = data['history']
        
        if not hist.empty:
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
            fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Chart data currently unavailable.")

        # D. PREDICTIONS & ANALYSTS
        st.subheader("🔮 Intelligence")
        col_ai, col_analyst = st.columns(2)
        with col_ai:
            st.info(f"**AI Trend (30 Days):** {data['ai_trend']}")
            if data['ai_price'] > 0: st.caption(f"Target: {data['currency']}{data['ai_price']:.2f}")
        with col_analyst:
            st.success(f"**Wall St. Consensus:** {data['analyst_rec']}")
            if data['analyst_target'] > 0: st.caption(f"Target: {data['currency']}{data['analyst_target']}")

        # E. MONETIZATION
        st.divider()
        st.subheader("🚀 Take Action")
        m1, m2 = st.columns(2)
        
        with m1:
             st.info("📉 **Start Trading**")
             if data['currency'] == "₹":
                 st.markdown("[**Open Zerodha Account**](#) \n\n Lowest fees in India.")
             else:
                 st.markdown("[**Open Robinhood Account**](#) \n\n Get a free stock.")
        
        with m2:
             st.success("📚 **Learn the Math**")
             st.markdown("[**Buy 'The Intelligent Investor'**](https://amzn.to/4jlK6gE) \n\n The book Warren Buffett recommends.")
        
        st.caption("Transparency: We may earn a commission if you use these links.")

    else:
        st.error(f"Could not load data for '{ticker}'. API might be busy or ticker is invalid.")
else:
    if not search_query:
        st.info("👆 Enter a stock to begin.")
        st.subheader("📩 Get Undervalued Stocks Weekly")
        email = st.text_input("Enter email for top 5 picks:", placeholder="you@example.com")
        if st.button("Subscribe Free"):
            st.success("Thanks! You are on the list.")


