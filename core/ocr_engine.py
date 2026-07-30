"""
J.A.R.V.I.S. OCR Engine
Fast text extraction from screen using Windows OCR API (via PowerShell)
and Tesseract as fallback. No LLM call needed — pure OCR.
"""

import subprocess
import json
import base64
import os
from io import BytesIO
from typing import Optional

import pyautogui
from PIL import Image


def ocr_screen(region: Optional[tuple] = None) -> str:
    """
    Extract text from the screen (or a region) using Windows OCR.
    
    Args:
        region: Optional (x, y, width, height) tuple to capture a specific area.
                If None, captures the full screen.
    
    Returns:
        Extracted text string.
    """
    # 1. Capture screenshot
    if region:
        img = pyautogui.screenshot(region=region)
    else:
        img = pyautogui.screenshot()

    img = img.convert("RGB")

    # Save to temp file for PowerShell OCR
    temp_path = os.path.join(os.environ.get("TEMP", "."), "jarvis_ocr_temp.png")
    img.save(temp_path, format="PNG")

    # 2. Try Windows OCR (built-in, fast)
    text = _windows_ocr(temp_path)
    if text:
        return text

    # 3. Fallback to Tesseract if installed
    text = _tesseract_ocr(temp_path)
    if text:
        return text

    return "OCR failed: Neither Windows OCR nor Tesseract returned results."


def _windows_ocr(image_path: str) -> str:
    """Use Windows 10/11 built-in OCR via PowerShell."""
    ps_script = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]

# Helper to await async WinRT calls
function Await($WinRtTask, $ResultType) {{
    $asTask = $WinRtTask.GetAwaiter()
    while (-not $asTask.IsCompleted) {{ Start-Sleep -Milliseconds 50 }}
    return $asTask.GetResult()
}}

try {{
    # Load image
    $file = [Windows.Storage.StorageFile]::GetFileFromPathAsync("{image_path}")
    $storageFile = Await $file ([Windows.Storage.StorageFile])
    
    $stream = $storageFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)
    $randomStream = Await $stream ([Windows.Storage.Streams.IRandomAccessStream])
    
    $decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($randomStream)
    $bmpDecoder = Await $decoder ([Windows.Graphics.Imaging.BitmapDecoder])
    
    $bitmap = $bmpDecoder.GetSoftwareBitmapAsync()
    $softwareBmp = Await $bitmap ([Windows.Graphics.Imaging.SoftwareBitmap])
    
    # OCR
    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    $ocrResult = Await ($ocrEngine.RecognizeAsync($softwareBmp)) ([Windows.Media.Ocr.OcrResult])
    
    Write-Output $ocrResult.Text
}} catch {{
    Write-Output ""
}}
"""

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, timeout=15
        )
        text = result.stdout.strip()
        if text:
            return text
    except Exception as e:
        print(f"[OCR] Windows OCR error: {e}")

    return ""


def _tesseract_ocr(image_path: str) -> str:
    """Fallback OCR using Tesseract if installed."""
    try:
        result = subprocess.run(
            ["tesseract", image_path, "-", "--psm", "1"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass  # Tesseract not installed
    except Exception as e:
        print(f"[OCR] Tesseract error: {e}")

    return ""


def ocr_region(x: int, y: int, width: int, height: int) -> str:
    """Extract text from a specific screen region."""
    return ocr_screen(region=(x, y, width, height))
