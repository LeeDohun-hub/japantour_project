"""한국 여행 일본인 전용 안내 챗봇 (Streamlit)"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY".upper())
AIHUB_APIKEY = os.getenv("AIHUB_APIKEY")

if not OPENAI_API_KEY:
    st.warning("환경변수 OPENAI_API_KEY가 설정되지 않았습니다. .env를 확인해주세요.")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


st.set_page_config(
    page_title="韓国旅行案内チャットボット",
    page_icon="🛫",
    layout="wide",
)

st.title("🛫 韓国旅行案内チャットボット（日・韓対応）")
st.caption("韓国を旅行する日本人向けのガイド用チャットボットです。日本語または韓国語で質問できます。")

with st.sidebar:
    st.subheader("使い方")
    st.markdown(
        """
        - 日本語 または 韓国語 で質問してください  
          例）  
          - 「ソウルでおすすめの観光地は？」  
          - 「金浦空港から明洞までの行き方は？」  
          - 「冬に韓国旅行する時の服装は？」  

        - 回答は**観光ガイドの目線**で、  
          初めて韓国に来る日本人にも分かりやすく説明します。
        """
    )

    st.markdown(
        """
        **[한국어 안내]**

        - 한국어로도 질문할 수 있습니다.  
          예)  
          - "일본인이 많이 가는 서울 관광지는 어디예요?"  
          - "김포공항에서 명동까지 어떻게 가나요?"  
          - "겨울에 한국여행 갈 때 옷은 어떻게 준비해야 하나요?"
        """
    )

    reply_language = st.radio(
        "응답 언어 / Response language",
        options=["日本語", "한국어"],
        index=0,
    )

    if AIHUB_APIKEY:
        st.success("AIHUB_APIKEY が .env から読み込まれました。")
    else:
        st.info("AIHUB_APIKEY が見つ지 않았습니다（필수는 아닙니다）。")

    if st.button("会話をリセット"):
        st.session_state.messages = []
        st.rerun()


if "messages" not in st.session_state:
    st.session_state.messages = []


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # 한국어 번역이 저장되어 있는 경우 함께 표시
        if message.get("translated_ko"):
            st.markdown("---")
            st.markdown("### 한국어 번역")
            st.markdown(message["translated_ko"])


def build_system_prompt(reply_language: str) -> str:
    if reply_language == "한국어":
        return (
            "당신은 한국을 여행하는 일본인 관광객을 돕는 전문 한국어 여행 가이드입니다. "
            "질문은 한국어 또는 일본어로 들어올 수 있지만, 사용자가 선택한 언어인 **한국어**로만 대답해야 합니다. "
            "말투는 친절하고 공손하게 유지하고, 처음 한국을 방문하는 일본인도 이해하기 쉽도록 설명하세요. "
            "관광지, 맛집, 쇼핑, 교통수단, 계절별 옷차림, 문화/예절(마너) 등도 함께 제안해 주세요. "
            "가능하다면 일본인이 읽기 쉬우도록 장소 이름 뒤에 일본어(가타카나)를 병기해도 좋습니다."
        )
    return (
        "あなたは韓国を旅行する日本人観光客向けのプロの日本語ツアーガイドです。"
        "質問は日本語または韓国語で届きますが、回答は必ず**日本語**で行ってください。"
        "丁寧で親切な口調を使い、初めて韓国に来る人にも分かりやすく説明してください。"
        "観光地・グルメ・ショッピング・交通手段・季節ごとの服装・マナーなども提案してください。"
        "具体的な場所名やエリア名（例：明洞、弘大、江南、釜山、済州島 など）を挙げて説明するときは、"
        "日本人が読んで分かりやすいように、できればカタカナ（＋必要ならハングル）も併記してください。"
    )


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

    return completion.choices[0].message.content


def chat_with_openai(user_message: str, reply_language: str) -> str:
    if client is None:
        return "OpenAI APIキーが設定されていないため、回答を生成できません。`.env` の `OPENAI_API_KEY` を設定してください。"

    messages = [{"role": "system", "content": build_system_prompt(reply_language)}]
    for msg in st.session_state.messages:
        if msg["role"] in ("user", "assistant"):
            messages.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                }
            )
    messages.append({"role": "user", "content": user_message})

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.7,
    )

    return completion.choices[0].message.content


if user_input := st.chat_input("韓国旅行について日本語または韓国語で質問してください..."):
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            # reply_language は sidebar で選択された値
            reply = chat_with_openai(user_input, reply_language)
            # 기본 출력(원문)
            st.markdown(reply)

            # 일본어 응답 선택 시, 전체 출력을 한국어로 번역해서 함께 표시
            translated_ko = None
            if reply_language == "日本語":
                st.markdown("---")
                st.markdown("### 한국어 번역")
                translated_ko = translate_to_korean(reply)
                st.markdown(translated_ko)

    # 대화 맥락에는 원문만 저장하고, 번역은 별도 필드에 저장 (다음 턴 프롬프트에는 원문만 사용)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": reply,
            "translated_ko": translated_ko,
        }
    )

