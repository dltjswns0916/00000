import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from streamlit_plotly_events import plotly_events
from math import radians, cos, sin, asin, sqrt

# 페이지 설정
st.set_page_config(page_title="아시아 지진 데이터 분석", layout="wide")

st.title("🌏 아시아 지역 지진 분석 대시보드")
st.caption("USGS 데이터를 기반으로 아시아 지역(M4.0+)의 지진 데이터 및 구텐베르크-리히터 에너지 환산 정보를 제공합니다.")

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

# 3. 일상생활 에너지와 상대 비교 함수
def get_energy_comparison(joules):
    smartphone_charge = 50000.0            # 스마트폰 1회 완충 (약 50 kJ)
    lightning_strike = 1000000000.0         # 번개 1회 (약 1 GJ)
    car_fuel_tank = 1800000000.0            # 휘발유 50L 완충 (약 1.8 GJ)
    atomic_bomb_hiroshima = 6.3e13          # 히로시마 원폭 (약 63 TJ)
    
    if joules < lightning_strike:
        ratio = joules / smartphone_charge
        return f"📱 **스마트폰 약 {ratio:,.1f}회** 완충할 수 있는 에너지"
    elif joules < atomic_bomb_hiroshima:
        ratio = joules / car_fuel_tank
        return f"🚗 **휘발유 승용차 약 {ratio:,.1f}대**의 연료 탱크를 채울 수 있는 에너지"
    else:
        ratio = joules / atomic_bomb_hiroshima
        return f"💥 **히로시마 원자폭탄 약 {ratio:,.1f}개**가 폭발할 때 나오는 에너지"

# 4. USGS API 데이터 로드
@st.cache_data(ttl=86400)
def load_earthquake_data():
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(days=365 * 3) # 최근 3년 데이터
    
    params = {
        "format": "geojson",
        "starttime": start_date.strftime("%Y-%m-%d"),
        "endtime": end_date.strftime("%Y-%m-%d"),
        "minmagnitude": 4.0,
        "minlatitude": -10.0,  # 아시아 범위 (남단)
        "maxlatitude": 60.0,   # 아시아 범위 (북단)
        "minlongitude": 60.0,  # 아시아 범위 (서단)
        "maxlongitude": 150.0, # 아시아 범위 (동단)
        "limit": 3000           # 응답 오류 방지용 개수 제한
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        if response.status_code != 200:
            st.error(f"USGS API 서버 응답 오류 (상태 코드: {response.status_code})")
            return pd.DataFrame()
            
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
            'energy_tnt_tons': energy_j / 4.184e9
        })
        
    df = pd.DataFrame(events)
    return df

with st.spinner("USGS 서버에서 아시아 지진 데이터를 수집하는 중입니다..."):
    df = load_earthquake_data()

if df.empty:
    st.warning("현재 지정한 조건에 해당하는 지진 데이터가 없거나 서버 응답이 원활하지 않습니다.")
else:
    # 사이드바 필터
    st.sidebar.header("데이터 필터")
    min_mag = st.sidebar.slider("최소 규모", 4.0, 9.0, 4.0, step=0.1)
    filtered_df = df[df['magnitude'] >= min_mag].reset_index(drop=True)

    st.sidebar.write(f"검색된 지진 수: **{len(filtered_df)}**건")

    if filtered_df.empty:
        st.info("선택한 규모 조건에 맞는 지진이 없습니다.")
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("📍 지진 발생 위치 지도 (점 클릭 시 해당 지진 선택)")
            st.caption("※ 아시아 영역으로 화면 범위가 고정되어 있습니다.")
            
            # 백하얀 현상을 방지하기 위해 scatter_geo 사용 및 아시아 영역 고정
            fig = px.scatter_geo(
                filtered_df,
                lat="latitude",
                lon="longitude",
                size="magnitude",
                color="magnitude",
                color_continuous_scale="Reds",
                hover_name="place",
                hover_data={"time": True, "magnitude": True, "latitude": False, "longitude": False},
                projection="natural earth",
                height=600
            )
            
            # 아시아 대륙 경계 및 범위 가두기
            fig.update_geos(
                center=dict(lat=25, lon=105),
                lataxis_range=[-10, 60],
                lonaxis_range=[60, 150],
                showcountries=True,
                countrycolor="LightGrey",
                showcoastlines=True,
                coastlinecolor="Gray",
                showland=True,
                landcolor="WhiteSmoke",
                showocean=True,
                oceancolor="AliceBlue"
            )
            
            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            
            # 지도에서 점 클릭 이벤트 수신
            selected_points = plotly_events(fig, click_event=True, hover_event=False)

        # 클릭한 위치 연동 로직
        selected_idx = 0
        if selected_points:
            clicked_point = selected_points[0]
            point_lat = clicked_point.get('lat')
            point_lon = clicked_point.get('lon')
            
            if point_lat is not None and point_lon is not None:
                matching_rows = filtered_df[
                    (filtered_df['latitude'].round(2) == round(point_lat, 2)) & 
                    (filtered_df['longitude'].round(2) == round(point_lon, 2))
                ]
                if not matching_rows.empty:
                    selected_idx = matching_rows.index[0]

        with col2:
            st.subheader("🎯 특정 지진 선택 및 주변 분석")
            
            event_options = filtered_df.apply(
                lambda x: f"[{x['time'].strftime('%Y-%m-%d')}] 규모 {x['magnitude']} - {x['place']}", axis=1
            )
            
            selected_idx = st.selectbox(
                "분석할 지진을 선택하거나 지도상의 점을 직접 누르세요:", 
                range(len(event_options)), 
                index=selected_idx,
                format_func=lambda x: event_options[x]
            )
            
            selected_event = filtered_df.iloc[selected_idx]
            
            st.markdown("---")
            st.markdown("### 📌 선택한 지진 상세 정보")
            st.write(f"- **발생 일시:** {selected_event['time'].strftime('%Y-%m-%d %H:%M:%S')} (UTC)")
            st.write(f"- **위치:** {selected_event['place']}")
            st.write(f"- **규모 (Magnitude):** M{selected_event['magnitude']}")
            st.write(f"- **구텐베르크-리히터 방출 에너지:** `{selected_event['energy_joules']:.3e}` Joules")
            st.write(f"  *(약 TNT {selected_event['energy_tnt_tons']:,.2f} 톤)*")
            
            # 에너지 상대 비교
            st.info(f"💡 **에너지 크기 비교 예시:**\n\n" + get_energy_comparison(selected_event['energy_joules']))

        # 반경 100km 및 이후 지진 발생 분석
        st.markdown("---")
        st.subheader("🔍 선택 지진 '이후' 반경 내 지진 발생 빈도 및 에너지 분석")

        radius_km = st.slider("주변 탐색 반경 설정 (km)", 10, 500, 100, step=10)

        distances = filtered_df.apply(
            lambda row: haversine(selected_event['longitude'], selected_event['latitude'], row['longitude'], row['latitude']),
            axis=1
        )

        # 반경 내 + 선택된 지진 이후 발생 지진 필터링
        nearby_after_df = filtered_df[
            (distances <= radius_km) & 
            (filtered_df['time'] > selected_event['time'])
        ].copy()
        
        nearby_after_df['distance_km'] = distances[nearby_after_df.index]

        col_stat1, col_stat2, col_stat3 = st.columns(3)
        col_stat1.metric("선택 지진 이후 발생 빈도", f"{len(nearby_after_df)} 회")
        col_stat2.metric("이후 지진 총 방출 에너지 (TNT 톤)", f"{nearby_after_df['energy_tnt_tons'].sum():,.2f} 톤")
        col_stat3.metric("이후 발생 최대 규모", f"{nearby_after_df['magnitude'].max() if not nearby_after_df.empty else '-'}")

        # 주변 지진 목록 표
        st.markdown(f"**선택 지진 발생 이후 반경 {radius_km}km 내에서 일어난 지진 목록**")
        if nearby_after_df.empty:
            st.write("해당 지진 발생 이후 반경 내 추가 발생한 지진이 없습니다.")
        else:
            st.dataframe(
                nearby_after_df[['time', 'magnitude', 'place', 'distance_km', 'energy_joules']]
                .sort_values(by='time', ascending=True)
                .rename(columns={
                    'time': '발생 일시',
                    'magnitude': '규모',
                    'place': '위치',
                    'distance_km': '중심과의 거리(km)',
                    'energy_joules': '에너지(Joule)'
                }),
                use_container_width=True
            )
