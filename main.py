import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="아시아 지진 모니터링",
    page_icon="🌏",
    layout="wide"
)

# 1. 클릭한 지진 정보 상태 유지 (다른 점을 누르기 전까지 유지를 위한 session_state)
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
            coords = geom["coordinates"]
            
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

# 메인 화면 레이아웃
col_map, col_info = st.columns([2.3, 1])

with col_map:
    st.subheader("🌏 지진 분포 지도")
    
    # 지도를 자유롭게 움직여도 초기화되지 않도록 중심좌표 설정
    m = folium.Map(
        location=[20.0, 100.0],
        zoom_start=3,
        tiles="OpenStreetMap"
    )
    
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

    # 핵심 1: key 고정 및 returned_objects=["last_object_clicked"] 설정
    # 지도 이동/확대 시 발생하는 bounds 변경 이벤트를 무시하여 선택 정보가 초기화되는 현상을 방지함
    map_data = st_folium(
        m,
        width="100%",
        height=580,
        returned_objects=["last_object_clicked"],
        key="asia_earthquake_map"
    )

    # 핵심 2: 새로운 마커(점)를 클릭했을 때만 session_state 업데이트
    if map_data and map_data.get("last_object_clicked"):
        clicked = map_data["last_object_clicked"]
        c_lat, c_lng = clicked.get("lat"), clicked.get("lng")
        
        if c_lat is not None and c_lng is not None:
            # 클릭 좌표 위치의 데이터 탐색
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
    
    # 다른 점을 클릭하기 전까지 지속적으로 표출
    if st.session_state["selected_earthquake"]:
        eq = st.session_state["selected_earthquake"]
        st.write(f"• **발생 일시:** {eq['time']} (UTC)")
        st.write(f"• **위치:** {eq['place']}")
        st.write(f"• **위도 / 경도:** {eq['latitude']:.3f}°, {eq['longitude']:.3f}°")
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
