import time
from core.wake_word import WakeWordDetector
import logging

logging.basicConfig(level=logging.INFO)

def on_detected():
    print(">>> WAKE WORD DETECTED! <<<")

detector = WakeWordDetector(wake_word="hey_jarvis", threshold=0.3)
detector.on_wake_word = on_detected
detector.start()

print("Listening for wake word (threshold 0.3)... Press Ctrl+C to stop.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    detector.stop()
