import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
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
        "limit": 1000
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
            'id': feature.get('id', ''),
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
    # 1. 세션 상태 초기화 (클릭된 지진 고유 ID 보존)
    if 'selected_eq_id' not in st.session_state:
        st.session_state.selected_eq_id = df.iloc[0]['id'] if not df.empty else None

    # 사이드바 필터
    st.sidebar.header("데이터 필터")
    min_mag = st.sidebar.slider("최소 규모", 4.0, 9.0, 4.0, step=0.1)
    filtered_df = df[df['magnitude'] >= min_mag].reset_index(drop=True)

    st.sidebar.write(f"검색된 지진 수: **{len(filtered_df)}**건")

    if filtered_df.empty:
        st.info("선택한 규모 조건에 맞는 지진이 없습니다.")
    else:
        # 필터링 후 선택된 ID가 범위 밖이면 첫 번째 항목으로 변경
        if st.session_state.selected_eq_id not in filtered_df['id'].values:
            st.session_state.selected_eq_id = filtered_df.iloc[0]['id']

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("📍 지진 발생 위치 지도")
            st.caption("※ 아시아 지역 밖으로는 이동할 수 없으며 확대/축소만 가능합니다. 빨간 점을 누르면 상세 정보가 즉시 업데이트됩니다.")
            
            # 아시아 이동 제한 경계 [[남위/서경], [북위/동경]]
            asia_max_bounds = [[-10.0, 60.0], [60.0, 150.0]]
            
            # Folium 지도 생성 (아시아 영역 이외로 스크롤/이동 제한 설정)
            m = folium.Map(
                location=[25.0, 105.0],
                zoom_start=3,
                min_zoom=3,
                max_zoom=10,
                max_bounds=True,
                max_bounds_viscosity=1.0,  # 지도 이동을 아시아 경계 내로 완벽히 바운딩
                tiles="OpenStreetMap"
            )
            
            # 경계 상한선 고정
            m.fit_bounds(asia_max_bounds)

            for idx, row in filtered_df.iterrows():
                radius = max(4, (row['magnitude'] - 3) * 3)
                is_selected = (row['id'] == st.session_state.selected_eq_id)
                
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=radius,
                    color='#0055FF' if is_selected else 'darkred',
                    weight=3 if is_selected else 1,
                    fill=True,
                    fill_color='#0088FF' if is_selected else '#FF0000',
                    fill_opacity=0.9 if is_selected else 0.7,
                    tooltip=f"M{row['magnitude']} - {row['place']}",
                    popup=row['id']  # 점 클릭 시 ID 전달
                ).add_to(m)

            # 지도 반환 데이터 수신
            # returned_objects를 'last_object_clicked_popup' 하나만 지정하여 
            # 마우스 이동이나 Zoom 조작 시 무분별한 리셋(Rerun) 현상을 완전히 차단합니다.
            map_data = st_folium(
                m, 
                width="100%", 
                height=600, 
                key="asia_earthquake_map",
                returned_objects=["last_object_clicked_popup"]
            )

            # 지도 클릭 수신 시 ID 세션 업데이트 및 rerun
            if map_data and map_data.get("last_object_clicked_popup"):
                clicked_id = map_data["last_object_clicked_popup"]
                if clicked_id != st.session_state.selected_eq_id and clicked_id in filtered_df['id'].values:
                    st.session_state.selected_eq_id = clicked_id
                    st.rerun()

        # 현재 선택되어 있는 지진 Row 데이터 추출
        selected_row_idx = filtered_df[filtered_df['id'] == st.session_state.selected_eq_id].index[0]
        selected_event = filtered_df.iloc[selected_row_idx]

        with col2:
            st.subheader("🎯 특정 지진 선택 및 주변 분석")
            
            event_options = filtered_df.apply(
                lambda x: f"[{x['time'].strftime('%Y-%m-%d')}] M{x['magnitude']} - {x['place']}", axis=1
            )
            
            def on_select_change():
                idx = st.session_state.selectbox_idx
                st.session_state.selected_eq_id = filtered_df.iloc[idx]['id']

            st.selectbox(
                "분석할 지진을 선택하거나 지도상의 빨간 점을 직접 누르세요:", 
                range(len(event_options)), 
                index=int(selected_row_idx),
                format_func=lambda x: event_options[x],
                key="selectbox_idx",
                on_change=on_select_change
            )
            
            st.markdown("---")
            # 내가 점을 눌렀을 때 또는 목록에서 선택했을 때 해당 지진의 상세 정보가 이 위치에 바로 바뀝니다.
            st.markdown("### 📌 선택한 지진 상세 정보")
            st.write(f"- **발생 일시:** {selected_event['time'].strftime('%Y-%m-%d %H:%M:%S')} (UTC)")
            st.write(f"- **위치:** {selected_event['place']}")
            st.write(f"- **위도 / 경도:** `{selected_event['latitude']:.3f}°`, `{selected_event['longitude']:.3f}°`")
            st.write(f"- **규모 (Magnitude):** M{selected_event['magnitude']}")
            st.write(f"- **구텐베르크-리히터 방출 에너지:** `{selected_event['energy_joules']:.3e}` Joules")
            st.write(f"  *(약 TNT {selected_event['energy_tnt_tons']:,.2f} 톤)*")
            
            st.info(f"💡 **에너지 크기 비교 예시:**\n\n" + get_energy_comparison(selected_event['energy_joules']))

        # 반경 분석 섹션
        st.markdown("---")
        st.subheader("🔍 선택 지진 '이후' 반경 내 지진 발생 빈도 및 에너지 분석")

        radius_km = st.slider("주변 탐색 반경 설정 (km)", 10, 500, 100, step=10)

        distances = filtered_df.apply(
            lambda row: haversine(selected_event['longitude'], selected_event['latitude'], row['longitude'], row['latitude']),
            axis=1
        )

        nearby_after_df = filtered_df[
            (distances <= radius_km) & 
            (filtered_df['time'] > selected_event['time'])
        ].copy()
        
        nearby_after_df['distance_km'] = distances[nearby_after_df.index]

        col_stat1, col_stat2, col_stat3 = st.columns(3)
        col_stat1.metric("선택 지진 이후 발생 빈도", f"{len(nearby_after_df)} 회")
        col_stat2.metric("이후 지진 총 방출 에너지 (TNT 톤)", f"{nearby_after_df['energy_tnt_tons'].sum():,.2f} 톤")
        col_stat3.metric("이후 발생 최대 규모", f"{nearby_after_df['magnitude'].max() if not nearby_after_df.empty else '-'}")

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
