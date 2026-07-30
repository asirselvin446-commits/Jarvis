import wave
import struct
import math
import os

def generate_blip():
    # Generate a futuristic double-blip (like an activation sound)
    sample_rate = 44100
    duration1 = 0.05
    duration2 = 0.08
    gap = 0.02
    
    freq1 = 880.0  # A5
    freq2 = 1108.7 # C#6
    
    # Save to assets/wake.wav
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir)
        
    path = os.path.join(assets_dir, 'wake.wav')
    
    with wave.open(path, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        
        # Tone 1
        for i in range(int(sample_rate * duration1)):
            # fade in and out envelope
            env = math.sin(math.pi * i / (sample_rate * duration1))
            val = math.sin(2.0 * math.pi * freq1 * i / sample_rate) * env
            # soft volume
            val = int(val * 8000)
            wav.writeframes(struct.pack('h', val))
            
        # Gap
        for i in range(int(sample_rate * gap)):
            wav.writeframes(struct.pack('h', 0))
            
        # Tone 2
        for i in range(int(sample_rate * duration2)):
            env = math.sin(math.pi * i / (sample_rate * duration2))
            val = math.sin(2.0 * math.pi * freq2 * i / sample_rate) * env
            val = int(val * 8000)
            wav.writeframes(struct.pack('h', val))
            
    print(f"Created {path}")

if __name__ == "__main__":
    generate_blip()
