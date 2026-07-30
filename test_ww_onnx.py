import openwakeword
from openwakeword.model import Model
import numpy as np

try:
    model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    np.random.seed(42)
    audio_chunk = np.random.randint(-32768, 32767, size=1280, dtype=np.int16)
    prediction = model.predict(audio_chunk)
    print("Prediction on noise with ONNX:", prediction)
except Exception as e:
    print(f"Error during inference: {e}")
