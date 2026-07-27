import json
import requests
import streamlit as st

# SWIM API設定
LOGIN_URL = "https://top.swim.mlit.go.jp/swim/webapi/login"
ATIS_URL = "https://web.swim.mlit.go.jp/f2atrq/web/FLV402001"

AIRPORTS = [
    ("RJCC", "NEW CHITOSE"),
    ("RJCH", "HAKODATE"),
    ("RJSS", "SENDAI"),
    ("RJAA", "NARITA INTL"),
    ("RJTT", "HANEDA INTL"),
    ("RJSN", "NIIGATA"),
    ("RJGG", "CHUBU CENTRAIR"),
    ("RJOO", "OSAKA INTL"),
    ("RJBB", "KANSAI INTL"),
    ("RJBE", "KOBE"),
    ("RJOA", "HIROSHIMA"),
    ("RJOT", "TAKAMATSU"),
    ("RJOM", "MATSUYAMA"),
    ("RJOK", "KOCHI"),
    ("RJFF", "FUKUOKA"),
    ("RJFS", "SAGA"),
    ("RJFU", "NAGASAKI"),
    ("RJFT", "KUMAMOTO"),
    ("RJFO", "OITA"),
    ("RJFM", "MIYAZAKI"),
    ("RJFK", "KAGOSHIMA"),
    ("ROAH", "NAHA"),
    ("ROIG", "ISHIGAKI"),
]

st.set_page_config(page_title="SWIM ATIS Viewer", layout="wide")

# CSSによるボタン内テキストの2段折り返し＆スタイルデザイン設定
st.markdown(
    """
<style>
    div.stButton > button {
        height: 60px !important;
        white-space: pre-wrap !important; /* 改行を有効化 */
        line-height: 1.2 !important;
        padding: 4px 8px !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("D-ATIS VIEWER // RYOCC")


# SWIM自動ログイン処理（Secretsから読み込み）
def get_swim_session():
    if "session" in st.session_state and st.session_state.session is not None:
        return st.session_state.session

    try:
        account_id = st.secrets["swim"]["account_id"]
        password = st.secrets["swim"]["password"]
    except Exception:
        st.error(
            "システムエラー: SWIM認証情報がSecretsに設定されていません。"
        )
        return None

    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)",
            "Accept": "application/json, text/plain, */*",
        }
    )

    try:
        resp = sess.post(
            LOGIN_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"id": account_id, "password": password}),
            timeout=10,
        )
        if resp.status_code == 200:
            for c in list(sess.cookies):
                sess.cookies.set(
                    c.name,
                    c.value,
                    domain=c.domain,
                    path="/",
                    secure=c.secure,
                )
            st.session_state.session = sess
            return sess
        else:
            st.error(
                f"SWIMログインエラー (HTTP status: {resp.status_code})"
            )
            return None
    except Exception as e:
        st.error(f"通信エラー: {e}")
        return None


# --- メイン処理 ---
sess = get_swim_session()

if sess:
    # 選択UI形式の切り替え
    ui_mode = st.radio(
        "View Mode:",
        ["Button Mode", "Pull-down Mode"],
        horizontal=True,
    )

    selected_icao = None

    # A) ボタン一覧モード
    if "ボタン選択" in ui_mode:
        cols = st.columns(5)
        for idx, (icao, name) in enumerate(AIRPORTS):
            col = cols[idx % 5]
            # \nで改行を入れ、下段を小さめのフォント風にするテキスト構成
            button_text = f"{icao}\n{name}"
            if col.button(button_text, key=f"btn_{icao}", use_container_width=True):
                selected_icao = icao

    # B) プルダウンモード（スマホ推奨）
    else:
        options = [f"{icao} - {name}" for icao, name in AIRPORTS]
        selected_option = st.selectbox(
            "空港を選択してください:",
            options,
            index=None,
            placeholder="タップして空港を選択...",
        )
        if selected_option:
            selected_icao = selected_option.split(" - ")[0]

    # --- ATISデータ表示エリア ---
    if selected_icao:
        st.divider()
        st.subheader(f"ATIS Data: {selected_icao}")

        with st.spinner("ATISを取得中..."):
            try:
                resp = sess.get(
                    ATIS_URL,
                    params={"location": selected_icao, "dispcnt": 3},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    atis_entries = data.get("data", [])
                    if not atis_entries:
                        st.info("現在利用可能なATIS情報はありません。")
                    for entry in atis_entries:
                        info_list = entry.get(
                            "atisInfo", entry.get("atisinfo", [])
                        )
                        for info in info_list:
                            st.code(info, language="text")
                else:
                    st.error("ATISの取得に失敗しました。")
            except Exception as e:
                st.error(f"取得エラー: {e}")
