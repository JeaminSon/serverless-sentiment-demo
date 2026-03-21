
import streamlit as st
import boto3
import pandas as pd
import plotly.express as px
import os
from datetime import datetime


USER_ID = st.secrets.get("USER_ID", "jambread")       
USER_PW = st.secrets.get("USER_PW", "jambreadson77!")


def login():
    """로그인 화면을 처리하고 인증 상태를 반환합니다."""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.subheader("🔒 대시보드 접근 인증")
        input_id = st.text_input("아이디")
        input_pw = st.text_input("비밀번호", type="password")
        
        if st.button("로그인"):
            if input_id == USER_ID and input_pw == USER_PW:
                st.session_state.logged_in = True
                st.rerun() 
            else:
                st.error("아이디 또는 비밀번호가 잘못되었습니다.")
        return False
    return True

# 페이지 설정 (들여쓰기 없음)
st.set_page_config(page_title="감성 분석 실시간 모니터링", layout="wide")

# --- 메인 실행부: 로그인 성공 시에만 아래 모든 코드가 실행됨 ---
if login():
    st.title("📊 감성 분석 서비스 실시간 대시보드")
    
    # [1] 데이터 로딩 함수 정의
    @st.cache_data(ttl=60)
    def load_data():
        try:
            dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
            table = dynamodb.Table('SentimentAnalysisLog')
            response = table.scan()
            items = response.get('Items', [])
            
            if not items:
                return pd.DataFrame()
                
            df = pd.DataFrame(items)
            # 데이터 타입 변환 및 정렬
            df['datetime'] = pd.to_datetime(df['timestamp'].astype(float), unit='s')
            df['latency_ms'] = df['latency_ms'].astype(float)
            df = df.sort_values('datetime')
            return df
        except Exception as e:
            st.error(f"데이터를 불러오는 중 오류 발생: {e}")
            return pd.DataFrame()

    # [2] 데이터 불러오기 실행
    df = load_data()

    # [3] 화면 구성 (데이터 유무에 따라 분기)
    if df.empty:
        st.warning("현재 DynamoDB에 저장된 데이터가 없습니다. 웹사이트에서 테스트를 진행해 주세요!")
    else:
        # 상단 요약 지표 (Metrics)
        col1, col2, col3 = st.columns(3)
        col1.metric("총 분석 횟수", f"{len(df)}회")
        col2.metric("평균 응답 속도", f"{df['latency_ms'].mean():.1f} ms")
        col3.metric("최근 분석 결과", str(df['label'].iloc[-1]))

        st.divider()

        # 그래프 영역 (좌: 파이 차트 / 우: 라인 차트)
        left_col, right_col = st.columns(2)

        with left_col:
            st.subheader("전체 감성 분포 비중")
            fig_pie = px.pie(df, names='label', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)

        with right_col:
            st.subheader("시간별 응답 지연 시간(ms)")
            fig_line = px.line(df, x='datetime', y='latency_ms', markers=True)
            st.plotly_chart(fig_line, use_container_width=True)

        # 하단 상세 데이터 테이블
        st.subheader("🔍 최신 로그 데이터 (최근 10건)")
        st.dataframe(df[['datetime', 'label', 'confidence', 'latency_ms']].tail(10), 
                     use_container_width=True)
        
        # 로그아웃 버튼 (선택 사항)
        if st.sidebar.button("로그아웃"):
            st.session_state.logged_in = False
            st.rerun()