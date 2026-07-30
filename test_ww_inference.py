import openwakeword
from openwakeword.model import Model
import numpy as np

try:
    model = Model(wakeword_models=["hey_jarvis"])
    audio_chunk = np.zeros(1280, dtype=np.int16)
    prediction = model.predict(audio_chunk)
    print("Prediction:", prediction)
except Exception as e:
    print(f"Error during inference: {e}")
