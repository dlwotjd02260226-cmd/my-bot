import threading
import copy

class DataHub:
    def __init__(self):
        # 데이터를 저장할 빈 딕셔너리 공간과 충돌 방지용 잠금장치(Lock)를 만듭니다.
        self.data = {}
        self.lock = threading.Lock()

    def update(self, key, value):
        # 웹소켓 쓰레드가 데이터를 안전하게 메모리에 받아 적는 함수입니다.
        with self.lock:
            self.data[key] = copy.deepcopy(value)

    def get(self, key):
        # 전략 엔진이 계산을 위해 메모리에서 안전하게 복사본을 꺼내가는 함수입니다.
        with self.lock:
            return copy.deepcopy(self.data.get(key, None))

# 다른 파일들이 이 한 장부를 같이 바라보도록 전역 객체(hub)를 생성합니다.
hub = DataHub()
