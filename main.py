# main.py（以下のコードを貼り付け）
import json
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 環境変数の読み込み
load_dotenv()

# Trello API設定
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
LIST_ID = "6799ead0c1d4ba691fabf5ad"  # 対象のリストID

# Google Calendar設定
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")


def get_board_name(board_id):
    """ボード名を取得"""
    url = f"https://api.trello.com/1/boards/{board_id}"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN, "fields": "name"}
    response = requests.get(url, params=params)
    return response.json().get("name", "Unknown Board")


def get_trello_cards():
    """Trelloカードを取得"""
    url = f"https://api.trello.com/1/lists/{LIST_ID}/cards"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    return requests.get(url, params=params).json()


def convert_utc_to_jst(utc_str):
    """UTC→JST変換"""
    if not utc_str:
        return None, None
    try:
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in utc_str else "%Y-%m-%dT%H:%M:%SZ"
        utc_date = datetime.strptime(utc_str, fmt)
        jst_date = utc_date + timedelta(hours=9)
        return jst_date.strftime("%Y-%m-%d"), jst_date.strftime("%H:%M:%S")
    except Exception as e:
        print(f"日付変換エラー: {e}")
        return None, None


def create_calendar_event(service, card):
    """カレンダーイベント作成"""
    start_date, start_time = convert_utc_to_jst(card.get("start") or card.get("due"))
    due_date, due_time = convert_utc_to_jst(card.get("due"))

    if not all([start_date, due_date]):
        print(f"スキップ: {card.get('name')} (日付不正)")
        return

    event = {
        "summary": f"{get_board_name(card['idBoard'])} - {card['name']}",
        "start": {
            "dateTime": f"{start_date}T{start_time or '09:00:00'}",
            "timeZone": "Asia/Tokyo",
        },
        "end": {
            "dateTime": f"{due_date}T{due_time or '18:00:00'}",
            "timeZone": "Asia/Tokyo",
        },
    }

    try:
        service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print(f"登録成功: {card['name']}")
    except Exception as e:
        print(f"エラー: {str(e)}")


def get_google_credentials():
    """オフライン認証フローを使用"""
    credentials_json = os.getenv("GOOGLE_CREDENTIALS")
    if not credentials_json:
        raise ValueError("GOOGLE_CREDENTIALSが設定されていません")

    credentials_info = json.loads(credentials_json)
    flow = InstalledAppFlow.from_client_config(
        credentials_info,
        SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",  # ブラウザ不要のリダイレクトURI
    )

    # 認証URLを表示
    auth_url, _ = flow.authorization_url(prompt="consent")
    print(f"以下のURLにアクセスして認証コードを取得してください: {auth_url}")

    # 認証コードを入力
    auth_code = input("認証コードを入力: ")
    return flow.fetch_token(code=auth_code)


def main():
    """メイン処理"""
    creds = get_google_credentials()
    service = build("calendar", "v3", credentials=creds)

    for card in get_trello_cards():
        create_calendar_event(service, card)


if __name__ == "__main__":
    main()
