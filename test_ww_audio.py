import pyttsx3
import wave
import numpy as np

# Generate TTS
engine = pyttsx3.init()
engine.setProperty('rate', 150)
engine.save_to_file('hey jarvis', 'test_ww.wav')
engine.runAndWait()

# Read the WAV file
with wave.open('test_ww.wav', 'rb') as wf:
    # Need to resample to 16kHz? pyttsx3 usually saves at 22050 or 16000
    framerate = wf.getframerate()
    print(f"Framerate: {framerate}")
    frames = wf.readframes(wf.getnframes())
    audio_data = np.frombuffer(frames, dtype=np.int16)

import openwakeword
from openwakeword.model import Model

model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")

# Feed in chunks
chunk_size = 1280
max_score = 0.0

for i in range(0, len(audio_data), chunk_size):
    chunk = audio_data[i:i+chunk_size]
    if len(chunk) < chunk_size:
        # pad
        chunk = np.pad(chunk, (0, chunk_size - len(chunk)), 'constant')
    
    prediction = model.predict(chunk)
    score = prediction.get('hey_jarvis', 0.0)
    if score > max_score:
        max_score = score
        print(f"New max score: {max_score}")

print(f"Final max score: {max_score}")
