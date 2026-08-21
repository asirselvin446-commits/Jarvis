"""
J.A.R.V.I.S. OCR Engine
Fast text extraction from screen using Windows OCR API (via PowerShell)
and Tesseract as fallback. Upgraded to Semantic OCR with bounding box tracking,
element classification, and clickability detection.
"""

import subprocess
import json
import base64
import os
import re
from io import BytesIO
from typing import Optional, List, Dict, Any

import pyautogui
from PIL import Image


def _ps_quote(value: str) -> str:
    """Quote a string as a PowerShell single-quoted literal.

    Single-quoted PowerShell strings interpolate nothing, so a path containing
    ``$`` or a backtick is passed through verbatim; embedded single quotes are
    escaped by doubling them.
    """
    return "'" + str(value).replace("'", "''") + "'"


class SemanticElement:
    """Represents a semantically classified UI element extracted via OCR & visual layout analysis."""

    def __init__(
        self,
        text: str,
        category: str,
        clickable: bool,
        x: int,
        y: int,
        width: int,
        height: int,
        confidence: float = 0.85,
        context: str = ""
    ):
        self.text = text.strip()
        self.category = category  # "Button", "Input", "Header", "Text", "Link"
        self.clickable = clickable
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.center_x = x + width // 2
        self.center_y = y + height // 2
        self.confidence = confidence
        self.context = context

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "category": self.category,
            "clickable": self.clickable,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "confidence": self.confidence,
            "context": self.context
        }

    def __repr__(self) -> str:
        return f"<SemanticElement [{self.category}] '{self.text}' @ ({self.center_x}, {self.center_y})>"


def ocr_screen(region: Optional[tuple] = None) -> str:
    """
    Extract text from the screen (or a region) using Windows OCR.
    
    Args:
        region: Optional (x, y, width, height) tuple to capture a specific area.
    Returns:
        Extracted text string.
    """
    if region:
        img = pyautogui.screenshot(region=region)
    else:
        img = pyautogui.screenshot()

    img = img.convert("RGB")

    temp_path = os.path.join(os.environ.get("TEMP", "."), "jarvis_ocr_temp.png")
    img.save(temp_path, format="PNG")

    text = _windows_ocr(temp_path)
    if text:
        return text

    text = _tesseract_ocr(temp_path)
    if text:
        return text

    return "OCR failed: Neither Windows OCR nor Tesseract returned results."


def semantic_ocr_screen(region: Optional[tuple] = None) -> List[SemanticElement]:
    """
    Perform semantic OCR returning classified UI elements with bounding boxes and clickability flags.
    """
    if region:
        img = pyautogui.screenshot(region=region)
        offset_x, offset_y = region[0], region[1]
    else:
        img = pyautogui.screenshot()
        offset_x, offset_y = 0, 0

    img = img.convert("RGB")
    temp_path = os.path.join(os.environ.get("TEMP", "."), "jarvis_ocr_temp.png")
    img.save(temp_path, format="PNG")

    lines_with_boxes = _windows_ocr_words(temp_path)
    semantic_elements = []

    for line in lines_with_boxes:
        text = line.get("text", "").strip()
        if not text:
            continue

        x = line.get("x", 0) + offset_x
        y = line.get("y", 0) + offset_y
        w = line.get("w", 10)
        h = line.get("h", 10)

        # Categorize element based on textual & geometric heuristics
        category, clickable = _classify_element(text, w, h)
        semantic_elements.append(
            SemanticElement(
                text=text,
                category=category,
                clickable=clickable,
                x=x,
                y=y,
                width=w,
                height=h,
                confidence=line.get("confidence", 0.85),
                context=f"Position: ({x},{y})"
            )
        )

    return semantic_elements


def _classify_element(text: str, width: int, height: int) -> tuple:
    """Classify text into (category, clickable) using string patterns and bounding shape."""
    t_lower = text.lower()
    
    # Button heuristics
    button_words = ["submit", "send", "click", "search", "ok", "cancel", "login", "sign in", "save", "next", "back", "open", "close", "confirm"]
    if any(bw in t_lower for bw in button_words) or (len(text) <= 15 and height > 15 and width < 200):
        return "Button", True

    # Input field label heuristics
    input_words = ["search", "type", "enter", "email", "username", "password", "message", "write", "find"]
    if any(iw in t_lower for iw in input_words) and ("..." in text or "here" in t_lower or ":" in text):
        return "Input", True

    # Link heuristics
    if t_lower.startswith("http") or t_lower.startswith("www") or ".com" in t_lower or "learn more" in t_lower:
        return "Link", True

    # Header heuristics
    if height >= 24 or (len(text) < 40 and text.isupper()):
        return "Header", False

    return "Text", False


# PowerShell prelude that loads the WinRT OCR types and defines a working
# ``Await``. WinRT async operations come back as System.__ComObject, which has
# no ``GetAwaiter()`` — calling it throws and silently yields no OCR at all.
# The supported route is reflecting over WindowsRuntimeSystemExtensions.AsTask
# to convert the IAsyncOperation into a .NET Task we can wait on.
_PS_WINRT_PRELUDE = r"""
# OCR output is routinely non-ASCII; without this PowerShell emits the console
# codepage and the Python side fails to decode it.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]

$candidates = @([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -like 'IAsyncOperation*' })
if ($candidates.Count -eq 0) { Write-Output ''; exit }
$script:asTaskGeneric = $candidates[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $script:asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

# Decode an image file into a SoftwareBitmap and run OCR over it.
# NOTE: never call .GetType() on any of these — they are WinRT types and it throws.
function Get-OcrResult([string]$Path) {
    $storageFile  = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
    $randomStream = Await ($storageFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $bmpDecoder   = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($randomStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $softwareBmp  = Await ($bmpDecoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $ocrEngine    = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $ocrEngine) { return $null }
    return Await ($ocrEngine.RecognizeAsync($softwareBmp)) ([Windows.Media.Ocr.OcrResult])
}
"""


def _windows_ocr(image_path: str) -> str:
    """Use Windows 10/11 built-in OCR via PowerShell."""
    ps_script = _PS_WINRT_PRELUDE + """
try {
    $ocrResult = Get-OcrResult -Path %IMAGE%
    if ($null -ne $ocrResult) { Write-Output $ocrResult.Text } else { Write-Output "" }
} catch {
    Write-Output ""
}
""".replace("%IMAGE%", _ps_quote(image_path))

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        text = result.stdout.strip()
        if text:
            return text
    except Exception as e:
        print(f"[OCR] Windows OCR error: {e}")

    return ""


def _windows_ocr_words(image_path: str) -> List[Dict[str, Any]]:
    """Extract text lines and bounding boxes using Windows WinRT OCR.

    Each line's box spans every word in it, so the derived centre lands in the
    middle of the line. (It previously used only the first word's rect, which
    put the click target on the line's opening character.)
    """
    ps_script = _PS_WINRT_PRELUDE + """
try {
    $ocrResult = Get-OcrResult -Path %IMAGE%
    if ($null -eq $ocrResult) { Write-Output "[]"; exit }

    $items = New-Object System.Collections.ArrayList
    foreach ($line in $ocrResult.Lines) {
        if ($line.Words.Count -eq 0) { continue }
        # Union of every word rect = the true extent of the line.
        $left = [double]::MaxValue; $top = [double]::MaxValue
        $right = [double]::MinValue; $bottom = [double]::MinValue
        foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            if ($r.X -lt $left) { $left = $r.X }
            if ($r.Y -lt $top) { $top = $r.Y }
            if (($r.X + $r.Width) -gt $right) { $right = $r.X + $r.Width }
            if (($r.Y + $r.Height) -gt $bottom) { $bottom = $r.Y + $r.Height }
        }
        $null = $items.Add([PSCustomObject]@{
            text = $line.Text
            x = [int]$left
            y = [int]$top
            w = [int]($right - $left)
            h = [int]($bottom - $top)
            confidence = 0.90
        })
    }
    if ($items.Count -eq 0) { Write-Output "[]" }
    else { ConvertTo-Json -InputObject @($items) -Compress }
} catch {
    Write-Output "[]"
}
""".replace("%IMAGE%", _ps_quote(image_path))

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        out = result.stdout.strip()
        if out and out.startswith("["):
            return json.loads(out)
        elif out and out.startswith("{"):
            return [json.loads(out)]
    except Exception as e:
        print(f"[OCR] Windows word OCR error: {e}")

    return []


def _tesseract_ocr(image_path: str) -> str:
    """Fallback OCR using Tesseract if installed."""
    try:
        result = subprocess.run(
            ["tesseract", image_path, "-", "--psm", "1"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[OCR] Tesseract error: {e}")

    return ""


def ocr_region(x: int, y: int, width: int, height: int) -> str:
    """Extract text from a specific screen region."""
    return ocr_screen(region=(x, y, width, height))
