import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import yfinance as yf
from bs4 import BeautifulSoup
import os

st.set_page_config(page_title="나만의 투자 포트폴리오", layout="wide")
DATA_FILE = os.path.join(os.path.dirname(__file__), "my_portfolio.csv")

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE, dtype={'매수단가': float, '보유수량': float})
    else:
        return pd.DataFrame({
            '종목명': ['삼성전자', 'SK하이닉스', '비트코인'],
            '매수단가': [75000.0, 180000.0, 90000000.0],
            '보유수량': [100.0, 50.0, 0.5]
        }).astype({'매수단가': float, '보유수량': float})

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# 실시간 환율 조회 함수
def get_exchange_rate():
    try:
        rate = yf.Ticker("KRW=X")
        val = rate.history(period="1d")['Close'].iloc[-1]
        return float(val) if val > 0 else 1350.0
    except:
        return 1350.0

def get_current_price(ticker):
    # 1. 가상화폐 (업비트)
    if ticker in ['비트코인', 'BTC', '이더리움', 'ETH']:
        upbit_tickers = {'비트코인': 'KRW-BTC', 'BTC': 'KRW-BTC', '이더리움': 'KRW-ETH', 'ETH': 'KRW-ETH'}
        market_code = upbit_tickers.get(ticker)
        try:
            url = f"https://api.upbit.com/v1/ticker?markets={market_code}"
            return float(requests.get(url).json()[0]['trade_price'])
        except:
            return 0.0
            
    # 2. 국내 주식 및 국내 상장 ETF
    kr_tickers = {
        '삼성전자': '005930.KS',
        'SK하이닉스': '000660.KS',
        'KODEX 미국S&P500': '360750.KS',
        'KODEX 미국나스닥100': '379810.KS'
    }
    if ticker in kr_tickers:
        try:
            stock = yf.Ticker(kr_tickers[ticker])
            data = stock.history(period="5d")
            return float(data['Close'].iloc[-1]) if not data.empty else 0.0
        except:
            return 0.0
            
    # 3. 미국 주식 및 기타 영문 티커 (GOOGL, NVDA, PLTR 등)
    else:
        try:
            # 야후 파이낸스 객체 생성 시 영문 티커 공백 제거 및 대문자 보정
            clean_ticker = ticker.strip().upper()
            stock = yf.Ticker(clean_ticker)
            data = stock.history(period="5d")
            if not data.empty:
                return float(data['Close'].iloc[-1])
            else:
                # 데이터가 안 잡히면 1일 데이터로 재시도
                data_1d = stock.history(period="1d")
                if not data_1d.empty:
                    return float(data_1d['Close'].iloc[-1])
            return 0.0
        except Exception as e:
            print(f"미국 주식 조회 에러 ({ticker}): {e}")
            return 0.0

def update_portfolio(ticker, price, qty, trade_type):
    df = st.session_state.portfolio.copy()
    updated_rows = []
    found = False
    
    for _, row in df.iterrows():
        name = row['종목명']
        qty_val = float(row['보유수량'])
        price_val = float(row['매수단가'])
        
        if name == ticker:
            found = True
            if trade_type == "매수":
                new_qty = qty_val + qty
                new_avg = ((qty_val * price_val) + (qty * price)) / new_qty
                updated_rows.append({'종목명': name, '매수단가': new_avg, '보유수량': new_qty})
            elif trade_type == "매도" and qty_val > qty:
                updated_rows.append({'종목명': name, '매수단가': price_val, '보유수량': qty_val - qty})
        else:
            updated_rows.append({'종목명': name, '매수단가': price_val, '보유수량': qty_val})
            
    if not found and trade_type == "매수":
        updated_rows.append({'종목명': ticker, '매수단가': float(price), '보유수량': float(qty)})
        
    st.session_state.portfolio = pd.DataFrame(updated_rows)
    st.session_state.portfolio = st.session_state.portfolio.astype({'매수단가': float, '보유수량': float})
    save_data(st.session_state.portfolio)
    return "성공"

st.title("📈 내 포트폴리오 현황")

if not st.session_state.portfolio.empty:
    df = st.session_state.portfolio.copy()
    df['현재가_raw'] = df['종목명'].apply(get_current_price)
    
    usd_krw = get_exchange_rate()
    
    domestic_list = ['삼성전자', 'SK하이닉스', 'KODEX 미국S&P500', 'KODEX 미국나스닥100', '비트코인', 'BTC', '이더리움', 'ETH']
    
    def process_financials(row):
        ticker = row['종목명']
        raw_price = row['현재가_raw']
        
        if ticker in domestic_list:
            return raw_price
        else:
            # 미국 주식이면 환율 곱하기 (만약 raw_price가 0이면 그대로 0 반환)
            return raw_price * usd_krw if raw_price > 0 else 0.0

    df['현재가'] = df.apply(process_financials, axis=1)
    df['보유금액'] = df['매수단가'] * df['보유수량']
    
    # [수정] 현재가가 0보다 크면 무조건 평가금액과 평가손익을 정상 계산
    df['평가금액'] = df.apply(lambda row: row['현재가'] * row['보유수량'] if row['현재가'] > 0 else 0, axis=1)
    df['평가손익'] = df.apply(lambda row: row['평가금액'] - row['보유금액'] if row['평가금액'] > 0 else 0, axis=1)
    
    # 수익률 계산
    def calc_return(row):
        if row['현재가'] <= 0 or row['보유금액'] <= 0:
            return None
        return round((row['평가손익'] / row['보유금액']) * 100, 2)

    df['평가손익률(%)'] = df.apply(calc_return, axis=1)
    
    # 현재가가 0이거나 nan이면 수익률 계산에서 제외하여 None 처리
    def calc_return(row):
        if row['현재가'] <= 0:
            return None
        return round((row['평가손익'] / row['보유금액']) * 100, 2)

    df['평가손익률(%)'] = df.apply(calc_return, axis=1)
    
    total_invested = df['보유금액'].sum()
    # 현재가가 정상적으로 들어온 것만 합산
    total_current = df[df['현재가'] > 0]['평가금액'].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("총 매수금액", f"{total_invested:,.0f} 원")
    col2.metric("총 평가금액", f"{total_current:,.0f} 원" if total_current > 0 else "조회 중...")
    if total_current > 0:
        col3.metric("총 평가손익", f"{total_current - total_invested:,.0f} 원", 
                    f"{(total_current - total_invested)/total_invested*100:.2f}%")
    else:
        col3.metric("총 평가손익", "계산 중")

    st.divider()

    col_table, col_chart = st.columns([1.5, 1])
    
    with col_table:
        st.subheader("종목별 상세 내역")
        display_df = df[['종목명', '보유수량', '매수단가', '현재가', '보유금액', '평가금액', '평가손익', '평가손익률(%)']].copy()
        
        # 데이터프레임의 숫자 컬럼들을 강제로 숫자형(float)으로 변환 (오류 방지)
        for col in ['보유수량', '매수단가', '현재가', '보유금액', '평가금액', '평가손익', '평가손익률(%)']:
            display_df[col] = pd.to_numeric(display_df[col], errors='coerce')

        # 화면에 보여주기 위해 문자열로 변환 (0보다 크면 원화 형식, 아니면 조회 실패)
        display_df['보유수량'] = display_df['보유수량'].apply(lambda x: f"{x:,.1f}" if pd.notnull(x) else "-")
        display_df['매수단가'] = display_df['매수단가'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) and x > 0 else "-")
        display_df['현재가'] = display_df['현재가'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) and x > 0 else "조회 실패")
        display_df['보유금액'] = display_df['보유금액'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) and x > 0 else "-")
        display_df['평가금액'] = display_df['평가금액'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) and x > 0 else "조회 실패")
        display_df['평가손익'] = display_df['평가손익'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "조회 실패")
        display_df['평가손익률(%)'] = display_df['평가손익률(%)'].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
        
        st.dataframe(display_df, hide_index=True)

    with col_chart:
        st.subheader("포트폴리오 비중")
        chart_df = df[df['평가금액'] > 0]
        if not chart_df.empty:
            fig = px.pie(chart_df, values='평가금액', names='종목명', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("포트폴리오가 비어있습니다. 아래에서 주식을 매수해 보세요!")

st.divider()

st.subheader("🔄 매매 기록 업데이트")
with st.form("trade_form"):
    t_col1, t_col2, t_col3, t_col4 = st.columns(4)
    with t_col1:
        trade_ticker = st.text_input("종목명 (예: 삼성전자 또는 NVDA)")
    with t_col2:
        trade_price = st.number_input("체결단가", min_value=0.0, step=100.0)
    with t_col3:
        trade_qty = st.number_input("수량", min_value=0.0, step=0.1)
    with t_col4:
        trade_type = st.selectbox("구분", ["매수", "매도"])
    
    submitted = st.form_submit_button("업데이트 적용")
    
    if submitted:
        if trade_ticker and trade_price > 0 and trade_qty > 0:
            result = update_portfolio(trade_ticker, trade_price, trade_qty, trade_type)
            if result == "성공":
                st.success(f"{trade_ticker} {trade_qty}주 {trade_type} 적용 완료!")
                st.rerun()
            else:
                st.error(result)
        else:
            st.warning("종목명, 단가, 수량을 정확히 입력해 주세요.")