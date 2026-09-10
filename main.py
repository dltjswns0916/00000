import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, cos, sin, asin, sqrt

st.set_page_config(
    page_title="아시아 지진 모니터링",
    page_icon="🌏",
    layout="wide"
)

# 두 위도/경도 간 거리(km) 계산 함수 (하버사인 공식)
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371.0 # 지구 반지름 (km)
    return c * r

# 1. 클릭한 지진 정보 상태 유지
if "selected_earthquake" not in st.session_state:
    st.session_state["selected_earthquake"] = None

# 2. USGS API 데이터 로드 함수
@st.cache_data(ttl=3600)
def load_earthquake_data(min_mag=4.0):
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude={min_mag}&limit=1000"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        eq_list = []
        for feature in data.get("features", []):
            props = feature["properties"]
            geom = feature["geometry"]
            coords = geom["coords"] if "coords" in geom else geom["coordinates"]
            
            lng, lat, depth = coords[0], coords[1], coords[2]
            mag = props["mag"]
            place = props["place"]
            time_ms = props["time"]
            time_str = pd.to_datetime(time_ms, unit="ms").strftime("%Y-%m-%d %H:%M:%S")
            
            # 구텐베르크-리히터 에너지 계산
            energy_joules = 10 ** (4.8 + 1.5 * mag) if mag else 0
            tnt_tons = energy_joules / 4.184e9
            
            eq_list.append({
                "id": feature["id"],
                "time": time_str,
                "place": place,
                "latitude": lat,
                "longitude": lng,
                "mag": mag,
                "depth": depth,
                "energy_joules": energy_joules,
                "tnt_tons": tnt_tons
            })
        return pd.DataFrame(eq_list)
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

# 세계 및 아시아 주요 도시 데이터
MAJOR_CITIES = [
    {"name": "🏛️ 서울 (Seoul)", "lat": 37.5665, "lng": 126.9780},
    {"name": "🏛️ 도쿄 (Tokyo)", "lat": 35.6762, "lng": 139.6503},
    {"name": "🏛️ 베이징 (Beijing)", "lat": 39.9042, "lng": 116.4074},
    {"name": "🏛️ 상하이 (Shanghai)", "lat": 31.2304, "lng": 121.4737},
    {"name": "🏛️ 타이베이 (Taipei)", "lat": 25.0330, "lng": 121.5654},
    {"name": "🏛️ 마닐라 (Manila)", "lat": 14.5995, "lng": 120.9842},
    {"name": "🏛️ 방콕 (Bangkok)", "lat": 13.7563, "lng": 100.5018},
    {"name": "🏛️ 자카르타 (Jakarta)", "lat": -6.2088, "lng": 106.8456},
    {"name": "🏛️ 싱가포르 (Singapore)", "lat": 1.3521, "lng": 103.8198},
    {"name": "🏛️ 쿠알라룸푸르 (Kuala Lumpur)", "lat": 3.1390, "lng": 101.6869},
    {"name": "🏛️ 뉴델리 (New Delhi)", "lat": 28.6139, "lng": 77.2090},
    {"name": "🏛️ 하노이 (Hanoi)", "lat": 21.0285, "lng": 105.8542},
    {"name": "🏛️ 타슈켄트 (Tashkent)", "lat": 41.2995, "lng": 69.2401},
    {"name": "🏛️ 울란바토르 (Ulaanbaatar)", "lat": 47.8864, "lng": 106.9057},
    {"name": "🏛️ 오사카 (Osaka)", "lat": 34.6937, "lng": 135.5023},
    {"name": "🏛️ 알마티 (Almaty)", "lat": 43.2220, "lng": 76.8512}
]

# 사이드바 데이터 및 반경 필터 설정
st.sidebar.title("⚙️ 설정 및 필터")
min_mag = st.sidebar.slider("최소 규모", min_value=2.0, max_value=8.0, value=4.0, step=0.1)

# 반경 슬라이더 (지도 상의 원 크기 및 위치에 동적 반영)
target_radius = st.sidebar.slider("탐색 반경 설정 (km)", min_value=100, max_value=1000, value=500, step=50)

df = load_earthquake_data(min_mag)
st.sidebar.write(f"검색된 지진 수: {len(df)}건")

# 메인 화면 상단 레이아웃
col_map, col_info = st.columns([2.3, 1])

with col_map:
    st.subheader("🌏 지진 분포 지도")
    
    # 선택된 지진이 있으면 그 점의 좌표를 중심으로 설정, 없으면 기본 중심 설정
    if st.session_state["selected_earthquake"]:
        sel_eq = st.session_state["selected_earthquake"]
        map_center = [sel_eq["latitude"], sel_eq["longitude"]]
        map_zoom = 5
    else:
        map_center = [20.0, 100.0]
        map_zoom = 4

    # 지도 생성 (국경선 및 주요 도시가 잘 보이는 세련된 CartoDB voyager 타일 적용)
    m = folium.Map(
        location=map_center,
        zoom_start=map_zoom,
        min_zoom=3,
        max_zoom=10,
        max_bounds=True,
        min_lat=-15.0,
        max_lat=60.0,
        min_lon=50.0,
        max_lon=150.0,
        tiles="CartoDB voyager"
    )
    
    # 주요 도시 표기 (은은한 점과 툴팁)
    cities_group = folium.FeatureGroup(name="주요 도시")
    for city in MAJOR_CITIES:
        folium.CircleMarker(
            location=[city["lat"], city["lng"]],
            radius=2.5,
            stroke=False,
            fill=True,
            fill_color="#333333",
            fill_opacity=0.7,
            tooltip=city["name"]
        ).add_to(cities_group)
    cities_group.add_to(m)

    # 선택한 지진 중심 반경 원 (설정한 km 크기와 클릭 위치에 동적 연동)
    if st.session_state["selected_earthquake"]:
        sel_eq = st.session_state["selected_earthquake"]
        folium.Circle(
            location=[sel_eq["latitude"], sel_eq["longitude"]],
            radius=target_radius * 1000,  # km -> m 변환
            color="#8A2BE2",
            fill=True,
            fill_color="#8A2BE2",
            fill_opacity=0.12,
            weight=1.5,
            tooltip=f"선택 지진 중심 반경 {target_radius:,}km"
        ).add_to(m)

    # 지진 마커 표시 (두꺼운 바깥선 제거 stroke=False, 가볍고 산뜻한 전체 색상 채우기)
    for _, row in df.iterrows():
        # 지진 규모별 색상 (밝은 레드 / 부드러운 주황 / 산뜻한 파랑)
        fill_color = "#FF5252" if row["mag"] >= 6.0 else "#FF9F43" if row["mag"] >= 5.0 else "#48DBFB"
        
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=max(3.5, row["mag"] * 1.5),
            stroke=False,          # 테두리 선을 없애 가벼운 느낌 부여
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.75,     # 투명도 조정하여 은은하게 채움
            popup=f"M{row['mag']} - {row['place']}",
            tooltip=f"M{row['mag']} ({row['time']})"
        ).add_to(m)

    # st_folium 실행
    map_data = st_folium(
        m,
        width="100%",
        height=580,
        returned_objects=["last_object_clicked"],
        key="asia_earthquake_map"
    )

    # 지진 마커 클릭 처리
    if map_data and map_data.get("last_object_clicked"):
        clicked = map_data["last_object_clicked"]
        c_lat, c_lng = clicked.get("lat"), clicked.get("lng")
        
        if c_lat is not None and c_lng is not None:
            tolerance = 0.005
            matched = df[
                (df["latitude"].between(c_lat - tolerance, c_lat + tolerance)) &
                (df["longitude"].between(c_lng - tolerance, c_lng + tolerance))
            ]
            if not matched.empty:
                new_selected = matched.iloc[0].to_dict()
                if not st.session_state["selected_earthquake"] or st.session_state["selected_earthquake"]["id"] != new_selected["id"]:
                    st.session_state["selected_earthquake"] = new_selected
                    st.rerun()

with col_info:
    # 드롭다운 목록과 상태 동기화
    if not df.empty:
        options = ["선택 안함"] + [f"[{row['time'][:10]}] M{row['mag']} - {row['place']}" for _, row in df.iterrows()]
        
        default_idx = 0
        if st.session_state["selected_earthquake"]:
            cur = st.session_state["selected_earthquake"]
            cur_label = f"[{cur['time'][:10]}] M{cur['mag']} - {cur['place']}"
            if cur_label in options:
                default_idx = options.index(cur_label)
        
        selected_option = st.selectbox(
            "지진 선택 목록",
            options=options,
            index=default_idx,
            key="earthquake_selectbox"
        )
        
        if selected_option != "선택 안함":
            idx = options.index(selected_option) - 1
            st.session_state["selected_earthquake"] = df.iloc[idx].to_dict()

    st.markdown("---")
    st.markdown("### 📌 선택한 지진 상세 정보")
    
    if st.session_state["selected_earthquake"]:
        eq = st.session_state["selected_earthquake"]
        st.write(f"• **발생 일시:** {eq['time']} (UTC)")
        st.write(f"• **위치:** {eq['place']}")
        st.write(f"• **위도 / 경도:** {eq['latitude']:.3f}°, {eq['longitude']:.3f}°")
        st.write(f"• **진원 깊이:** {eq['depth']} km")
        st.write(f"• **규모 (Magnitude):** M{eq['mag']}")
        st.write(f"• **구텐베르크-리히터 방출 에너지:** {eq['energy_joules']:.3e} Joules")
        st.write(f"*(약 TNT {eq['tnt_tons']:,.2f} 톤)*")
    else:
        st.info("지도의 마커(점)를 클릭하거나 목록에서 선택하세요.")

    st.markdown("---")
    with st.expander("💡 에너지 크기 예시"):
        st.markdown("""
        - **M4.0**: TNT 약 15톤
        - **M5.0**: TNT 약 480톤
        - **M6.0**: TNT 약 15,000톤
        - **M7.0**: TNT 약 48만 톤
        """)

# 하단 반경 발생 지진 탐색 섹션
st.markdown("---")
st.subheader("🌐 선택한 지진 기준 반경 내 발생 지진 탐색")

if st.session_state["selected_earthquake"] and not df.empty:
    selected_eq = st.session_state["selected_earthquake"]
    
    # 전체 지진 데이터셋과의 거리 계산
    df_calc = df.copy()
    df_calc["distance_km"] = df_calc.apply(
        lambda r: haversine(selected_eq["longitude"], selected_eq["latitude"], r["longitude"], r["latitude"]),
        axis=1
    )
    
    # 지정한 반경 내 지진 필터링
    nearby_df = df_calc[df_calc["distance_km"] <= target_radius].sort_values("distance_km").reset_index(drop=True)
    
    st.success(
        f"📍 기준 지진: **[{selected_eq['place']}]** (M{selected_eq['mag']})\n\n"
        f"👉 설정 반경 **0 ~ {target_radius:,} km** 이내에서 발생한 지진은 총 **{len(nearby_df)}건** 입니다. (왼쪽 사이드바에서 반경 조정 가능)"
    )
    
    st.markdown("#### 📋 반경 내 발생 지진 상세 리스트")
    
    for idx, row in nearby_df.iterrows():
        is_self = (row["id"] == selected_eq["id"])
        badge = " [선택된 지진 본인]" if is_self else ""
        
        with st.expander(f"#{idx+1} | M{row['mag']} - {row['place']} (거리: {row['distance_km']:.1f} km){badge}", expanded=(idx < 3)):
            st.write(f"• **발생 일시:** {row['time']} (UTC)")
            st.write(f"• **위치:** {row['place']}")
            st.write(f"• **위도 / 경도:** {row['latitude']:.3f}°, {row['longitude']:.3f}°")
            st.write(f"• **진원 깊이:** {row['depth']} km")
            st.write(f"• **규모 (Magnitude):** M{row['mag']}")
            st.write(f"• **기준 지진과의 거리:** {row['distance_km']:.1f} km")
            st.write(f"• **구텐베르크-리히터 방출 에너지:** {row['energy_joules']:.3e} Joules (TNT 약 {row['tnt_tons']:,.2f} 톤)")
else:
    st.info("지점 마커를 클릭하여 지진을 선택하시면 선택한 지진 기준 반경 내 발생한 지진 정보 목록이 이곳에 나타납니다.")
