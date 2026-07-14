import requests
import json
import time

def save_data():
    while True:
        # 1. OKX에서 1시간 봉 데이터 가져오기
        url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1h&limit=500"
        try:
            r = requests.get(url, timeout=2)
            data = r.json().get('data', [])
            if data:
                # 2. 데이터를 data.json 파일에 저장
                with open("data.json", "w") as f:
                    json.dump(data, f)
                print("데이터 업데이트 완료")
        except:
            print("데이터 업데이트 실패")
        time.sleep(60) # 1분마다 반복

if __name__ == "__main__":
    save_data()

