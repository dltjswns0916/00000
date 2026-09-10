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

# 하버사인(Haversine) 공식을 이용한 두 위도/경도 간 거리(km) 계산 함수
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371.0 # 지구 반지름 (km)
    return c * r

# 1. 선택한 지진 정보 상태 유지 (session_state)
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
            
            # 구텐베르크-리히터 에너지 계산 (Joules 및 TNT 환산)
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

# 사이드바 데이터 필터
st.sidebar.title("데이터 필터")
min_mag = st.sidebar.slider("최소 규모", min_value=2.0, max_value=8.0, value=4.0, step=0.1)

df = load_earthquake_data(min_mag)
st.sidebar.write(f"검색된 지진 수: {len(df)}건")

# 메인 화면 상단 레이아웃 (지도 & 선택 지진 상세정보)
col_map, col_info = st.columns([2.3, 1])

with col_map:
    st.subheader("🌏 지진 분포 지도")
    
    # [요구사항 반영 1] 지도가 아시아 밖으로 이동하지 못하도록 경계 고정 (max_bounds 적용)
    m = folium.Map(
        location=[20.0, 100.0],
        zoom_start=4,
        min_zoom=3,          # 축소 한계 지정 (너무 작아져서 외부 영역 보이는 것 방지)
        max_zoom=10,         # 확대는 가능
        max_bounds=True,     # 경계 고정 활성화
        min_lat=-15.0,       # 아시아 남단
        max_lat=60.0,        # 아시아 북단
        min_lon=50.0,        # 아시아 서단
        max_lon=150.0,       # 아시아 동단
        tiles="OpenStreetMap"
    )
    
    # 선택된 지진이 있는 경우 해당 위치에 반경 원(Circle) 표시
    if st.session_state["selected_earthquake"]:
        sel_eq = st.session_state["selected_earthquake"]
        folium.Circle(
            location=[sel_eq["latitude"], sel_eq["longitude"]],
            radius=1000 * 1000, # 1,000km (미터 단위)
            color="purple",
            fill=True,
            fill_color="purple",
            fill_opacity=0.1,
            weight=1.5,
            tooltip="반경 1,000km 범위"
        ).add_to(m)

    # 지진 마커 표시
    for _, row in df.iterrows():
        color = "red" if row["mag"] >= 6.0 else "orange" if row["mag"] >= 5.0 else "blue"
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=max(3, row["mag"] * 1.5),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.6,
            popup=f"M{row['mag']} - {row['place']}",
            tooltip=f"M{row['mag']} ({row['time']})"
        ).add_to(m)

    # st_folium 실행 (지도 이동 시 이벤트 초기화 방지)
    map_data = st_folium(
        m,
        width="100%",
        height=580,
        returned_objects=["last_object_clicked"],
        key="asia_earthquake_map"
    )

    # 새로운 점을 클릭했을 때 session_state 업데이트
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
                st.session_state["selected_earthquake"] = matched.iloc[0].to_dict()

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

# [요구사항 반영 2] 하단 반경 0~1000km 발생 지진 정보 칸 추가
st.markdown("---")
st.subheader("🌐 선택한 지진 기준 반경 내 발생 지진 탐색")

if st.session_state["selected_earthquake"] and not df.empty:
    selected_eq = st.session_state["selected_earthquake"]
    
    # 반경 범위 설정 슬라이더 (기본값 1000km)
    target_radius = st.slider("탐색 반경 설정 (km)", min_value=0, max_value=1000, value=1000, step=50)
    
    # 전체 지진 데이터셋과의 거리 계산
    df_calc = df.copy()
    df_calc["distance_km"] = df_calc.apply(
        lambda r: haversine(selected_eq["longitude"], selected_eq["latitude"], r["longitude"], r["latitude"]),
        axis=1
    )
    
    # 지정한 반경 내 지진 필터링 (거리순 정렬)
    nearby_df = df_calc[df_calc["distance_km"] <= target_radius].sort_values("distance_km").reset_index(drop=True)
    
    st.success(
        f"📍 기준 지진: **[{selected_eq['place']}]** (M{selected_eq['mag']})\n\n"
        f"👉 반경 **0 ~ {target_radius:,} km** 이내에서 발생한 지진은 총 **{len(nearby_df)}건** 입니다."
    )
    
    # 반경 내 지진들의 상세 정보 나열
    st.markdown("#### 📋 반경 내 발생 지진 상세 리스트")
    
    for idx, row in nearby_df.iterrows():
        # 자기 자신인지 타 지진인지 표기 구분
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
    st.info("지점 마커를 클릭하여 지진을 선택하시면 선택한 지진 기준 반경(0~1,000km) 내에 발생한 지진 정보 목록이 이곳에 나타납니다.")
