import json
import re
from datetime import datetime

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

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

# 自動更新の間隔（ミリ秒）。10分 = 600,000ms
AUTO_REFRESH_INTERVAL_MS = 10 * 60 * 1000

st.set_page_config(page_title="D-ATIS JAPAN", layout="centered")

# 10分ごとにスクリプトを自動再実行させる。
# これはブラウザの全体リロードではなく通常のStreamlit rerunなので、
# key付きウィジェット(selectbox)やsession_stateの内容は保持される。
st_autorefresh(interval=AUTO_REFRESH_INTERVAL_MS, key="atis_autorefresh")

# カスタムCSS: 画面要素の完全制御
st.markdown(
    """
    <style>
    /* 1. iPhoneでのキーボード自動起動（フォーカス）を防止 */
    div[data-baseweb="select"] input {
        inputmode: none !important;
        pointer-events: none !important;
    }
    
    # 2. ヘッダーリボン（Deployボタン・メニュー・ハンバーガーアイコン）を非表示
    header[data-testid="stHeader"] {
        display: none !important;
    }
    
    # 3. フッター（右下の「Made with Streamlit」やGitHubリンク）を非表示
    footer {
        display: none !important;
    }
    
    # 4. 画面上部の余白を調整してスッキリさせる
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# タイトル
st.title("D-ATIS//JP")


# SWIM自動ログイン処理（Secretsから読み込み）
def get_swim_session(force_relogin: bool = False):
    if not force_relogin and st.session_state.get("session") is not None:
        return st.session_state.session

    try:
        account_id = st.secrets["swim"]["account_id"]
        password = st.secrets["swim"]["password"]
    except Exception:
        st.error("システムエラー: SWIM認証情報がSecretsに設定されていません。")
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
            st.error(f"SWIMログインエラー (HTTP status: {resp.status_code})")
            return None
    except Exception as e:
        st.error(f"通信エラー: {e}")
        return None


def extract_report_id(atis_text: str):
    """
    'ATIS RJAA U\\n...' の "U" の部分（更新のたびに変わる識別子）を取り出す。
    自動更新時に「本当に内容が変わったか」を安価に判定するために使う。
    """
    if not atis_text:
        return None
    m = re.match(r"ATIS\s+\w+\s+(\S+)", atis_text)
    return m.group(1) if m else None


def fetch_atis(sess, icao: str, retry: bool = True):
    """
    ATIS情報リクエスト。セッションが切れていた場合(403等)は
    1回だけ自動で再ログインしてリトライする。
    """
    resp = sess.get(
        ATIS_URL,
        params={"location": icao, "dispcnt": 3},
        timeout=10,
    )

    if resp.status_code in (401, 403) and retry:
        new_sess = get_swim_session(force_relogin=True)
        if new_sess is None:
            return None
        return fetch_atis(new_sess, icao, retry=False)

    if resp.status_code != 200:
        st.error(f"ATISの取得に失敗しました。(HTTP {resp.status_code})")
        return None

    return resp.json()


# --- メイン処理 ---
sess = get_swim_session()

if sess:
    # 1. ドロップダウンボックス
    # key を明示することで、自動更新(rerun)をまたいでも選択状態が保持される
    options = [f"{icao} - {name}" for icao, name in AIRPORTS]
    selected_option = st.selectbox(
        "空港を選択してください:",
        options,
        index=None,
        placeholder="タップして空港を選択...",
        label_visibility="collapsed",
        key="selected_airport_option",
    )

    # 2. 結果表示（選択時のみ直下にそのままテキスト表示）
    if selected_option:
        selected_icao = selected_option.split(" - ")[0]

        # 空港ごとに前回取得した識別子を保持しておく場所
        if "atis_report_ids" not in st.session_state:
            st.session_state.atis_report_ids = {}

        with st.spinner(""):
            data = fetch_atis(sess, selected_icao)

        if data is not None:
            atis_entries = data.get("data", [])
            if not atis_entries:
                st.info("現在利用可能なATIS情報はありません。")
            else:
                # 最新のATIS識別子を取り出して、前回と比較
                first_info_list = atis_entries[0].get(
                    "atisInfo", atis_entries[0].get("atisinfo", [])
                )
                latest_text = first_info_list[0] if first_info_list else None
                new_id = extract_report_id(latest_text)
                prev_id = st.session_state.atis_report_ids.get(selected_icao)

                if new_id and prev_id and new_id != prev_id:
                    st.toast(
                        f"{selected_icao} のATISが更新されました（{prev_id} → {new_id}）",
                        icon="🔄",
                    )
                if new_id:
                    st.session_state.atis_report_ids[selected_icao] = new_id

                st.caption(f"最終更新チェック: {datetime.now().strftime('%H:%M:%S')}")

                for entry in atis_entries:
                    info_list = entry.get("atisInfo", entry.get("atisinfo", []))
                    for info in info_list:
                        st.code(info, language="text")
