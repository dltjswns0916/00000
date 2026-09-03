import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from math import radians, cos, sin, asin, sqrt

# 페이지 설정
st.set_page_config(page_title="아시아 지진 데이터 분석", layout="wide")

st.title("🌏 아시아 지역 지진 분석 대시보드")
st.caption("USGS 데이터를 기반으로 규모 4.0 이상의 아시아 지진 및 구텐베르크-리히터 에너지 환산 정보를 제공합니다.")

# 1. 하버사인 공식을 이용한 두 위경도 사이의 거리 계산 (km)
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371 # 지구 반지름 (km)
    return c * r

# 2. 구텐베르크-리히터 에너지 환산식 (Joules)
# log10(E) = 4.8 + 1.5 * M
def calculate_energy(mag):
    if pd.isna(mag) or mag is None:
        return 0.0
    log_e = 4.8 + 1.5 * float(mag)
    return 10 ** log_e

# 3. USGS API 데이터 로드 (아시아 영역 경계 및 규모 4.0 이상)
@st.cache_data(ttl=3600)
def load_earthquake_data():
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": "2023-01-01",
        "minmagnitude": 4.0,
        "minlatitude": -10.0,  # 아시아 범위 설정 (남단)
        "maxlatitude": 60.0,   # 아시아 범위 설정 (북단)
        "minlongitude": 60.0,  # 아시아 범위 설정 (서단)
        "maxlongitude": 150.0  # 아시아 범위 설정 (동단)
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()
    
    events = []
    for feature in data.get('features', []):
        props = feature['properties']
        coords = feature['geometry']['coordinates']
        
        mag = props['mag']
        if mag is None or mag < 4.0:
            continue
            
        energy_j = calculate_energy(mag)
        
        events.append({
            'title': props.get('title', ''),
            'place': props.get('place', '위치 정보 없음'),
            'time': pd.to_datetime(props['time'], unit='ms'),
            'magnitude': mag,
            'longitude': coords[0],
            'latitude': coords[1],
            'depth': coords[2],
            'energy_joules': energy_j,
            'energy_tnt_tons': energy_j / 4.184e9 # Joule -> TNT 톤 환산
        })
        
    df = pd.DataFrame(events)
    return df

with st.spinner("지진 데이터를 불러오는 중입니다..."):
    df = load_earthquake_data()

if df.empty:
    st.warning("불러올 지진 데이터가 없거나 네트워크 연결을 확인해주세요.")
else:
    # 사이드바 필터
    st.sidebar.header("데이터 필터")
    min_mag = st.sidebar.slider("최소 규모", 4.0, 9.0, 4.0, step=0.1)
    filtered_df = df[df['magnitude'] >= min_mag].reset_index(drop=True)

    st.sidebar.write(f"총 검색된 지진 수: **{len(filtered_df)}**건")

    if filtered_df.empty:
        st.info("조건에 맞는 지진 데이터가 없습니다.")
    else:
        # 메인 레이아웃
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("📍 지진 발생 위치 지도")
            
            fig = px.scatter_mapbox(
                filtered_df,
                lat="latitude",
                lon="longitude",
                size="magnitude",
                color="magnitude",
                color_continuous_scale="Reds",
                hover_name="place",
                hover_data={"time": True, "magnitude": True, "latitude": False, "longitude": False},
                zoom=2,
                height=550
            )
            fig.update_layout(mapbox_style="open-street-map")
            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("🎯 특정 지진 선택 및 주변 분석")
            
            # 지진 선택 목록
            event_options = filtered_df.apply(
                lambda x: f"[{x['time'].strftime('%Y-%m-%d')}] 규모 {x['magnitude']} - {x['place']}", axis=1
            )
            selected_idx = st.selectbox("분석할 지진을 선택하세요:", range(len(event_options)), format_func=lambda x: event_options[x])
            
            selected_event = filtered_df.iloc[selected_idx]
            
            st.markdown("---")
            st.markdown("**선택한 지진 상세 정보**")
            st.write(f"- **발생 일시:** {selected_event['time'].strftime('%Y-%m-%d %H:%M:%S')} (UTC)")
            st.write(f"- **위치:** {selected_event['place']}")
            st.write(f"- **규모:** {selected_event['magnitude']}")
            st.write(f"- **방출 에너지:** {selected_event['energy_joules']:.3e} Joules (약 TNT {selected_event['energy_tnt_tons']:,.2f} 톤)")

        # 반경 내 주변 지진 분석
        st.markdown("---")
        st.subheader("🔍 선택 지진 주변 발생 빈도 및 에너지 분석")

        radius_km = st.slider("주변 탐색 반경 설정 (km)", 50, 1000, 300, step=50)

        # 반경 거리 계산
        distances = filtered_df.apply(
            lambda row: haversine(selected_event['longitude'], selected_event['latitude'], row['longitude'], row['latitude']),
            axis=1
        )

        nearby_df = filtered_df[distances <= radius_km].copy()
        nearby_df['distance_km'] = distances[distances <= radius_km]

        col_stat1, col_stat2, col_stat3 = st.columns(3)
        col_stat1.metric("반경 내 지진 발생 빈도", f"{len(nearby_df)} 회")
        col_stat2.metric("총 방출 에너지 (TNT 톤)", f"{nearby_df['energy_tnt_tons'].sum():,.2f} 톤")
        col_stat3.metric("최대 규모", f"{nearby_df['magnitude'].max()}")

        # 주변 지진 목록 표 출력
        st.markdown(f"**반경 {radius_km}km 내 발생한 지진 목록**")
        st.dataframe(
            nearby_df[['time', 'magnitude', 'place', 'distance_km', 'energy_joules']]
            .sort_values(by='time', ascending=False)
            .rename(columns={
                'time': '발생 일시',
                'magnitude': '규모',
                'place': '위치',
                'distance_km': '중심과의 거리(km)',
                'energy_joules': '에너지(Joule)'
            }),
            use_container_width=True
        )
