import openwakeword
from openwakeword.model import Model

try:
    openwakeword.utils.download_models()
    paths = openwakeword.get_pretrained_model_paths()
    print("Available models:")
    for p in paths:
        print(p)
        
    model = Model(wakeword_models=["hey_jarvis"])
    print("Successfully loaded hey_jarvis model!")
except Exception as e:
    print(f"Error: {e}")
