"""
TrelloのタスクをGoogleカレンダーに自動同期するスクリプト（ボード名対応版）
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
def get_board_name(board_id):
    """ボードIDからボード名を取得"""
    try:
        url = f"https://api.trello.com/1/boards/{board_id}"
        params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN, "fields": "name"}

        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get("name", "無名のボード")

    except requests.exceptions.RequestException as e:
        print(f"ボード情報取得失敗: {board_id} - {str(e)}")
        return "不明なボード"


def get_trello_cards():
    """Trelloからカードリストを取得"""
    try:
        url = f"https://api.trello.com/1/lists/{LIST_ID}/cards"
        params = {
            "key": TRELLO_API_KEY,
            "token": TRELLO_TOKEN,
            "fields": "name,due,start,idBoard,url",
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
# ヘルパー関数
# ---------------------------
def get_existing_events(service):
    """既存のイベントを取得（TrelloカードID付き）"""
    events = {}
    try:
        results = (
            service.events()
            .list(
                calendarId=CALENDAR_ID, maxResults=2500, fields="items(id,description)"
            )
            .execute()
        )

        for item in results.get("items", []):
            if "TrelloカードID: " in item.get("description", ""):
                card_id = (
                    item["description"].split("TrelloカードID: ")[1].split("\n")[0]
                )
                events[card_id] = item["id"]
        return events

    except Exception as e:
        print(f"既存イベント取得エラー: {str(e)}")
        return {}


def update_or_create_event(service, card, existing_events):
    """イベントの更新または作成"""
    board_name = get_board_name(card.get("idBoard"))
    card_id = card["id"]
    event_id = existing_events.get(card_id)

    # 日付情報を取得
    start_date, start_time = convert_utc_to_jst(card.get("start") or card.get("due"))
    due_date, due_time = convert_utc_to_jst(card.get("due"))

    if not all([start_date, due_date]):
        print(f"スキップ: {card.get('name')} - 日付情報が不正です")
        return

    # イベントデータ
    event = {
        "summary": f"[{board_name}] {card['name']}",
        "description": f"TrelloカードID: {card_id}\nURL: {card.get('url', '')}",
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
        if event_id:  # 更新処理
            service.events().update(
                calendarId=CALENDAR_ID, eventId=event_id, body=event
            ).execute()
            print(f"更新成功: {card['name']}")
        else:  # 新規作成
            service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print(f"新規登録: {card['name']}")

    except Exception as e:
        print(f"イベント処理失敗: {card.get('name', '無名のカード')} - {str(e)}")


# ---------------------------
# メイン処理
# ---------------------------
def main():
    try:
        calendar_service = get_google_service()
        existing_events = get_existing_events(calendar_service)
        cards = get_trello_cards()

        if not cards:
            print("同期対象のカードが見つかりませんでした")
            return

        for card in cards:
            update_or_create_event(calendar_service, card, existing_events)

        print(
            f"処理完了: 新規{len(cards)-len(existing_events)}件 / 更新{len(existing_events)}件"
        )

    except Exception as e:
        print(f"致命的なエラー: {str(e)}")
        raise


if __name__ == "__main__":
    main()
