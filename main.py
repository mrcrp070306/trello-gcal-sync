"""
TrelloのタスクをGoogleカレンダーに自動同期するスクリプト
サービスアカウントを使用した完全自動化版
"""

import json
import os
from datetime import datetime, timedelta

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------
# 環境変数設定
# ---------------------------
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
LIST_ID = "6799ead0c1d4ba691fabf5ad"  # 同期対象のTrelloリストID
CALENDAR_ID = os.getenv(
    "GOOGLE_CALENDAR_ID", "primary"
)  # デフォルトはプライマリカレンダー


# ---------------------------
# Googleカレンダー認証処理
# ---------------------------
def get_google_service():
    """サービスアカウントを使用してGoogleカレンダーサービスを取得"""
    try:
        # 環境変数からサービスアカウント情報を取得
        credentials_json = os.getenv("SERVICE_ACCOUNT_JSON")
        if not credentials_json:
            raise ValueError("SERVICE_ACCOUNT_JSONが設定されていません")

        # 認証情報をロード
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info, scopes=["https://www.googleapis.com/auth/calendar"]
        )

        # カレンダーサービスを構築
        return build("calendar", "v3", credentials=credentials)

    except Exception as e:
        print(f"Google認証エラー: {str(e)}")
        raise


# ---------------------------
# Trello連携処理
# ---------------------------
def get_trello_cards():
    """Trelloからカードリストを取得"""
    try:
        url = f"https://api.trello.com/1/lists/{LIST_ID}/cards"
        params = {
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
            "fields": "name,due,start,idBoard",
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Trello APIエラー: {str(e)}")
        return []


# ---------------------------
# 日付変換処理
# ---------------------------
def convert_utc_to_jst(utc_str):
    """UTC日時を日本時間に変換"""
    if not utc_str:
        return None, None

    try:
        # フォーマット判定（ミリ秒含むかどうか）
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in utc_str else "%Y-%m-%dT%H:%M:%SZ"

        # UTC→JST変換
        utc_date = datetime.strptime(utc_str, fmt)
        jst_date = utc_date + timedelta(hours=9)

        return (
            jst_date.strftime("%Y-%m-%d"),  # 日付
            jst_date.strftime("%H:%M:%S"),  # 時間
        )

    except ValueError as e:
        print(f"日付変換失敗: {utc_str} - {str(e)}")
        return None, None


# ---------------------------
# カレンダーイベント作成処理
# ---------------------------
def create_calendar_event(service, card):
    """Googleカレンダーにイベントを作成"""
    try:
        # 日付情報を取得
        start_date, start_time = convert_utc_to_jst(
            card.get("start") or card.get("due")
        )
        due_date, due_time = convert_utc_to_jst(card.get("due"))

        # 必須チェック
        if not all([start_date, due_date]):
            print(f"スキップ: {card.get('name')} - 日付情報が不正です")
            return

        # イベントデータを構築
        event = {
            "summary": f"{card['name']}",
            "description": f"TrelloカードID: {card['id']}",
            "start": {
                "dateTime": f"{start_date}T{start_time or '09:00:00'}",
                "timeZone": "Asia/Tokyo",
            },
            "end": {
                "dateTime": f"{due_date}T{due_time or '18:00:00'}",
                "timeZone": "Asia/Tokyo",
            },
        }

        # イベントを登録
        service.events().insert(calendarId=CALENDAR_ID, body=event).execute()

        print(f"登録成功: {card['name']}")

    except Exception as e:
        print(f"イベント登録失敗: {card.get('name', '無名のカード')} - {str(e)}")


# ---------------------------
# メイン処理
# ---------------------------
def main():
    """メイン実行関数"""
    try:
        # サービスを初期化
        calendar_service = get_google_service()

        # Trelloからカードを取得
        cards = get_trello_cards()

        if not cards:
            print("同期対象のカードが見つかりませんでした")
            return

        # 各カードを処理
        for card in cards:
            create_calendar_event(calendar_service, card)

        print("同期処理が正常に完了しました")

    except Exception as e:
        print(f"致命的なエラーが発生しました: {str(e)}")
        raise


if __name__ == "__main__":
    main()
