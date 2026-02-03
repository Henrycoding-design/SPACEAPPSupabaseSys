import os

N2YO_KEYS = [k.strip() for k in os.getenv("N2YO_KEYS", "").split(",") if k.strip()]
if len(N2YO_KEYS) < 1:
    raise RuntimeError("No N2YO API keys provided")

class N2YOKeyManager:
    def __init__(self, keys):
        self.keys = keys
        self.index = 0

    def current(self):
        return self.keys[self.index]

    def rotate(self):
        if len(self.keys) > 1:
            self.index = (self.index + 1) % len(self.keys)
            print(f"[N2YO] Rotated API key → index {self.index}")
        return self.current()

key_manager = N2YOKeyManager(N2YO_KEYS)
