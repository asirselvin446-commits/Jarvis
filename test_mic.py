import pyaudio
import numpy as np
import time

def test_mic():
    p = pyaudio.PyAudio()
    default_in = p.get_default_input_device_info()
    print(f"Default input device: {default_in['name']}")
    
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1280
    )
    
    print("Recording for 3 seconds... Please speak.")
    max_peak = 0
    for _ in range(int(16000 / 1280 * 3)):
        data = stream.read(1280, exception_on_overflow=False)
        chunk = np.frombuffer(data, dtype=np.int16)
        peak = np.abs(chunk).max()
        if peak > max_peak:
            max_peak = peak
            
    print(f"Max volume peak recorded: {max_peak}")
    
    stream.stop_stream()
    stream.close()
    p.terminate()

if __name__ == "__main__":
    test_mic()
