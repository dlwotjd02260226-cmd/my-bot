import threading

class DataHub:
    def __init__(self):
        self.data = {}
        self.lock = threading.Lock()

    def update(self, key, value):
        with self.lock:
            self.data[key] = value

    def get(self, key):
        with self.lock:
            return self.data.get(key, None)

hub = DataHub()
