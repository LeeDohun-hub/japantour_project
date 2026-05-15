"""한국 여행 일본인 전용 안내 챗봇 (Streamlit) — 홈 / AI 채팅 분리"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from src.api.google_places_client import GooglePlacesClient, NearbyPlace, recommend_nearby_places

try:
    from streamlit_js_eval import get_geolocation
except ImportError:
    get_geolocation = None


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY".upper())
AIHUB_APIKEY = os.getenv("AIHUB_APIKEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

st.set_page_config(
    page_title="韓国旅行案内チャットボット",
    page_icon="🛫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Japan Tour — 한국 여행 가이드 테마 (Streamlit 전역 스타일)
st.markdown(
    """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;600;700&family=Outfit:wght@500;600;700&display=swap');
  html, body, [class*="css"]  { font-family: 'Noto Sans JP','Noto Sans KR','Segoe UI',sans-serif !important; }
  .stApp {
    background: linear-gradient(168deg,#0a0f18 0%,#121c2e 55%,#0d1422 100%) !important;
    background-attachment: fixed;
  }
  .stApp::before {
    content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
    background:
      radial-gradient(ellipse 120% 70% at 0% -15%, rgba(232,90,107,.12), transparent 52%),
      radial-gradient(ellipse 90% 55% at 100% 0%, rgba(212,168,83,.08), transparent 48%);
  }
  .block-container { padding-top: 1.25rem !important; max-width: 920px !important; position: relative; z-index: 1; }
  section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(18,28,48,.95) 0%, rgba(10,16,28,.98) 100%) !important;
    border-right: 1px solid rgba(212,168,83,.18) !important;
  }
  section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem !important; }
  section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    font-family: 'Outfit','Noto Sans JP',sans-serif !important;
    color: #f2efe8 !important;
    letter-spacing: 0.02em;
  }
  section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] li, section[data-testid="stSidebar"] span {
    color: #c5cdd8 !important;
  }
  section[data-testid="stSidebar"] .stRadio label { color: #e8eaef !important; }
  div[data-testid="stChatMessage"] {
    background: rgba(22,34,56,.45) !important;
    border: 1px solid rgba(212,168,83,.14) !important;
    border-radius: 14px !important;
    padding: 0.6rem 0.85rem !important;
    margin-bottom: 0.65rem !important;
    backdrop-filter: blur(8px);
  }
  div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
    color: #eef1f5 !important; line-height: 1.6 !important;
  }
  .stChatInput { border-radius: 12px !important; }
  div[data-testid="stChatInput"] {
    border: 1px solid rgba(212,168,83,.22) !important;
    border-radius: 12px !important;
    background: rgba(8,12,22,.55) !important;
  }
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#e85a6b 0%,#c73e50 100%) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    box-shadow: 0 6px 18px rgba(232,90,107,.28) !important;
  }
  .stButton > button { border-radius: 10px !important; }
  .jt-hero {
    padding: 1.1rem 1.25rem 1.15rem;
    border-radius: 16px;
    border: 1px solid rgba(212,168,83,.2);
    background: linear-gradient(135deg, rgba(30,58,95,.35) 0%, rgba(18,28,48,.75) 100%);
    margin-bottom: 1rem;
    box-shadow: 0 12px 40px rgba(0,0,0,.22);
  }
  .jt-hero h1 {
    font-family: 'Outfit','Noto Sans JP',sans-serif !important;
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    margin: 0 0 0.35rem 0 !important;
    background: linear-gradient(105deg,#fff 0%,#e8dcc8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .jt-hero .jt-badge {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #d4a853;
    background: rgba(212,168,83,.14);
    border: 1px solid rgba(212,168,83,.25);
    padding: 0.28rem 0.65rem;
    border-radius: 999px;
    margin-bottom: 0.55rem;
  }
  .jt-hero p { margin: 0; color: #a8b2c4 !important; font-size: 0.95rem !important; line-height: 1.5 !important; }
  h3 { color: #d4a853 !important; font-family: 'Outfit',sans-serif !important; }
  .jt-home-card {
    border: 1px solid rgba(212,168,83,.18);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    background: rgba(18,28,48,.55);
    margin-bottom: 0.75rem;
  }
</style>
""",
    unsafe_allow_html=True,
)

if not OPENAI_API_KEY:
    st.warning("환경변수 OPENAI_API_KEY가 설정되지 않았습니다. .env를 확인해주세요.")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
places_client = GooglePlacesClient(api_key=GOOGLE_MAPS_API_KEY)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_location" not in st.session_state:
    st.session_state.current_location = None

if "nearby_recommendations" not in st.session_state:
    st.session_state.nearby_recommendations = None

if "location_error" not in st.session_state:
    st.session_state.location_error = None

if "request_geolocation" not in st.session_state:
    st.session_state.request_geolocation = False

if "ui_page" not in st.session_state:
    st.session_state.ui_page = "home"


def _set_location(latitude: float, longitude: float, source: str) -> None:
    st.session_state.current_location = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "source": source,
    }
    st.session_state.location_error = None


def _place_status(place: NearbyPlace) -> str:
    if place.is_open_now is True:
        return "営業中"
    if place.is_open_now is False:
        return "営業時間外の可能性"
    return "営業時間未確認"


def _format_distance(place: NearbyPlace) -> str:
    if place.distance_meters is None:
        return "距離不明"
    if place.distance_meters >= 1000:
        return f"{place.distance_meters / 1000:.1f} km"
    return f"{place.distance_meters} m"


def _render_places(title: str, places: list[NearbyPlace]) -> None:
    st.markdown(f"#### {title}")
    if not places:
        st.info("近くで条件に合う場所を見つけられませんでした。半径を広げてみてください。")
        return

    for index, place in enumerate(places[:5], start=1):
        rating = f"⭐ {place.rating:.1f}" if place.rating else "評価なし"
        reviews = f" / {place.user_rating_count}件" if place.user_rating_count else ""
        maps_section = ""
        if place.google_maps_uri:
            maps_section = (
                f"Google Maps: [地図/経路を見る]({place.google_maps_uri})  \n"
                f"URL: `{place.google_maps_uri}`"
            )
        st.markdown(
            f"**{index}. {place.name}**  \n"
            f"特徴: {_format_distance(place)} · {rating}{reviews} · {_place_status(place)}  \n"
            f"住所: {place.address or '住所未登録'}  \n"
            f"{maps_section}"
        )


def render_nearby_recommendations() -> None:
    recommendations = st.session_state.nearby_recommendations
    if not recommendations:
        return

    location = st.session_state.current_location
    st.markdown("### 📍 現在地周辺のおすすめ")
    if location:
        st.caption(
            f"基準位置: {location['latitude']:.5f}, {location['longitude']:.5f} "
            f"({location['source']})"
        )

    col1, col2 = st.columns(2)
    with col1:
        _render_places("観光スポット", recommendations.get("tourist_attractions", []))
    with col2:
        _render_places("グルメ / カフェ", recommendations.get("cafes", []))


def translate_to_korean(text: str) -> str:
    """LLM을 사용해 임의의 텍스트를 자연스러운 한국어로 번역."""
    if client is None:
        return "번역 기능을 사용하려면 OPENAI_API_KEY가 필요합니다."

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional translator. "
                    "Translate the user's message into natural Korean. "
                    "답변은 반드시 한국어로만 작성하고, 다른 설명은 하지 마세요."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )

    return completion.choices[0].message.content or ""


def chat_with_openai(user_message: str, reply_language: str) -> str:
    """라우팅 파이프라인을 통해 답변을 생성합니다.

    분류 → RAG(내부 지식) → Places API(위치 있을 때) → LLM 순으로 데이터 소스를 사용합니다.
    """
    if client is None:
        return "OpenAI APIキーが設定されていないため、回答を生成できません。`.env` の `OPENAI_API_KEY` を設定してください。"

    location = st.session_state.get("current_location")

    try:
        from src.chain.router import route_and_answer
        result = route_and_answer(
            user_message=user_message,
            reply_language=reply_language,
            history=st.session_state.messages,
            openai_client=client,
            latitude=location["latitude"] if location else None,
            longitude=location["longitude"] if location else None,
        )
        return result.reply
    except Exception:
        # 라우터 임포트·실행 실패 시 안전 폴백
        lang_rule = (
            "回答は必ず日本語で行ってください。"
            if reply_language == "日本語"
            else "반드시 한국어로만 답변해 주세요."
        )
        fallback_system = (
            f"あなたは韓国旅行の案内ガイドです。{lang_rule}\n"
            "具体的な店舗名・施設名・住所は確認できるデータがない場合は生成しないでください。"
            "エリア名の紹介や一般的なアドバイスに留め、"
            "具体的な場所はNaver MapやGoogle Mapsで検索するよう案内してください。"
        )
        messages = [{"role": "system", "content": fallback_system}]
        for msg in st.session_state.messages[-12:]:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.3,
        )
        return completion.choices[0].message.content or ""


def render_sidebar() -> str:
    """화면 전환·설정. 응답 언어 문자열 반환."""
    with st.sidebar:
        st.subheader("画面 / 화면")
        nav_labels = ("🏠 ホーム", "💬 AIチャット")
        current = 0 if st.session_state.ui_page == "home" else 1
        nav = st.radio(
            "表示を切り替え",
            nav_labels,
            index=current,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.ui_page = "home" if nav == nav_labels[0] else "chat"

        st.divider()

        reply_language = st.radio(
            "응답 언어 / Response language",
            options=["日本語", "한국어"],
            index=0,
        )

        if st.session_state.ui_page == "chat":
            st.markdown(
                """
                **チャットのヒント**

                - 日本語・韓国語どちらでも質問OK  
                - 観光・交通・グルメ・マナーなど
                """
            )
            st.markdown(
                """
                **[한국어]** 예: 서울 관광 코스, 공항→명동 이동, 겨울 옷차림
                """
            )

            st.divider()
            st.subheader("📍 今いる場所から探す")
            st.caption("位置情報または座標で近くの観光地・カフェを表示します。")

            radius_meters = st.slider(
                "検索半径",
                min_value=300,
                max_value=3000,
                value=1000,
                step=100,
                format="%d m",
            )

            if not places_client.is_configured:
                st.warning("GOOGLE_MAPS_API_KEY が設定されていません。`.env` に追加してください。")

            if get_geolocation is None:
                st.info("現在地の自動取得には `streamlit-js-eval` のインストールが必要です。")
            else:
                if st.button("現在地を取得"):
                    st.session_state.request_geolocation = True

                if st.session_state.request_geolocation:
                    location_result = get_geolocation()
                    coords = (location_result or {}).get("coords", {})
                    if coords.get("latitude") and coords.get("longitude"):
                        _set_location(coords["latitude"], coords["longitude"], "browser")
                        st.session_state.request_geolocation = False
                        st.success("現在地を取得しました。")
                    else:
                        st.info("ブラウザの位置情報許可を待っています。")

            with st.expander("座標を手入力する"):
                manual_latitude = st.number_input(
                    "Latitude",
                    value=37.5665,
                    format="%.6f",
                )
                manual_longitude = st.number_input(
                    "Longitude",
                    value=126.9780,
                    format="%.6f",
                )
                if st.button("この座標を使う"):
                    _set_location(manual_latitude, manual_longitude, "manual")
                    st.success("座標を保存しました。")

            current_location = st.session_state.current_location
            if current_location:
                st.caption(
                    f"現在の基準位置: {current_location['latitude']:.5f}, "
                    f"{current_location['longitude']:.5f}"
                )

            if st.button("周辺おすすめを表示", type="primary"):
                if not places_client.is_configured:
                    st.session_state.location_error = "GOOGLE_MAPS_API_KEY が必要です。"
                elif not st.session_state.current_location:
                    st.session_state.location_error = "先に現在地を取得するか、座標を入力してください。"
                else:
                    try:
                        language_code = "ja" if reply_language == "日本語" else "ko"
                        st.session_state.nearby_recommendations = recommend_nearby_places(
                            latitude=st.session_state.current_location["latitude"],
                            longitude=st.session_state.current_location["longitude"],
                            radius_meters=radius_meters,
                            language_code=language_code,
                        )
                        st.session_state.location_error = None
                    except Exception as exc:
                        st.session_state.location_error = f"Google Places API 호출에 실패했습니다: {exc}"

            if st.session_state.location_error:
                st.error(st.session_state.location_error)

        if AIHUB_APIKEY:
            st.success("AIHUB_APIKEY が .env から読み込まれました。")
        else:
            st.info("AIHUB_APIKEY が見つ지 않았습니다（필수는 아닙니다）。")

        if st.session_state.ui_page == "chat":
            if st.button("会話をリセット"):
                st.session_state.messages = []
                st.rerun()

    return reply_language


def render_home() -> None:
    st.markdown(
        """
<div class="jt-hero">
  <span class="jt-badge">Korea · Japan Guide</span>
  <h1>🛫 韓国旅行案内</h1>
  <p>日本人向けの韓国旅行サポート。AIチャットで質問したり、ホームからサービス概要を確認できます。</p>
</div>
""",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            '<div class="jt-home-card"><h3>AIチャット</h3><p>観光・交通・グルメ・マナーを日・韓で質問。</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="jt-home-card"><h3>周辺検索</h3><p>チャット画面で現在地付近のスポット・カフェを表示（要 API キー）。</p></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="jt-home-card"><h3>日・韓対応</h3><p>応答言語を選べます。日本語回答時は韓国語訳も表示。</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown("##### ")
    if st.button("💬 AIチャットを開く", type="primary", use_container_width=True):
        st.session_state.ui_page = "chat"
        st.rerun()


def render_chat(reply_language: str) -> None:
    st.markdown("### 💬 AIチャット")
    st.caption("下の入力欄から日本語または韓国語で送信してください。左の「🏠 ホーム」でトップに戻れます。")

    render_nearby_recommendations()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("translated_ko"):
                st.markdown("---")
                st.markdown("### 한국어 번역")
                st.markdown(message["translated_ko"])

    if user_input := st.chat_input("韓国旅行について日本語または韓国語で質問してください..."):
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("考え中..."):
                reply = chat_with_openai(user_input, reply_language)
                st.markdown(reply)

                translated_ko = None
                if reply_language == "日本語":
                    st.markdown("---")
                    st.markdown("### 한국어 번역")
                    translated_ko = translate_to_korean(reply)
                    st.markdown(translated_ko)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": reply,
                "translated_ko": translated_ko,
            }
        )


reply_language = render_sidebar()

if st.session_state.ui_page == "home":
    render_home()
else:
    render_chat(reply_language)
