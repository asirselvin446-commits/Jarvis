"""
J.A.R.V.I.S. Accessibility Engine
Extracts the Windows UI Automation tree to get actual UI element names,
positions, types, and states. Much more reliable than vision-only approaches
for identifying clickable elements.
"""

import subprocess
import json
import re
from typing import List, Dict, Optional


def get_ui_tree(process_name: str = "", max_depth: int = 3) -> List[Dict]:
    """
    Extract the UI Automation tree using PowerShell and UIAutomation.
    Returns a list of UI elements with their properties.
    
    Args:
        process_name: Filter by process name (e.g., 'chrome'). Empty = foreground window.
        max_depth: Maximum depth of the tree to traverse.
    """
    # PowerShell script to extract UI elements from the foreground window
    ps_script = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$auto = [System.Windows.Automation.AutomationElement]

function Get-UIElements {
    param(
        [System.Windows.Automation.AutomationElement]$element,
        [int]$depth = 0,
        [int]$maxDepth = 3
    )
    
    if ($depth -gt $maxDepth) { return }
    
    $results = @()
    
    try {
        $rect = $element.Current.BoundingRectangle
        
        $item = @{
            Name = $element.Current.Name
            ControlType = $element.Current.ControlType.ProgrammaticName
            AutomationId = $element.Current.AutomationId
            ClassName = $element.Current.ClassName
            IsEnabled = $element.Current.IsEnabled
            X = [int]$rect.X
            Y = [int]$rect.Y
            Width = [int]$rect.Width
            Height = [int]$rect.Height
            CenterX = [int]($rect.X + $rect.Width / 2)
            CenterY = [int]($rect.Y + $rect.Height / 2)
            Depth = $depth
        }
        
        if ($item.Name -or $item.AutomationId) {
            $results += $item
        }
        
        # Get children
        $children = $element.FindAll(
            [System.Windows.Automation.TreeScope]::Children,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        
        foreach ($child in $children) {
            $results += Get-UIElements -element $child -depth ($depth + 1) -maxDepth $maxDepth
        }
    } catch {}
    
    return $results
}

"""
    if process_name:
        ps_script += f"""
$proc = Get-Process -Name "{process_name}" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc -and $proc.MainWindowHandle -ne 0) {{
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
}} else {{
    $root = $auto::FocusedElement
}}
"""
    else:
        ps_script += """
# Get the foreground window
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
}
"@
$hwnd = [Win32]::GetForegroundWindow()
if ($hwnd -ne [IntPtr]::Zero) {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
} else {
    $root = $auto::FocusedElement
}
"""

    ps_script += f"""
$elements = Get-UIElements -element $root -maxDepth {max_depth}
$elements | ConvertTo-Json -Depth 5
"""

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, timeout=15
        )

        if result.returncode != 0:
            print(f"[Accessibility] PowerShell error: {result.stderr[:200]}")
            return []

        output = result.stdout.strip()
        if not output:
            return []

        elements = json.loads(output)
        if isinstance(elements, dict):
            elements = [elements]

        return elements

    except json.JSONDecodeError:
        return []
    except subprocess.TimeoutExpired:
        print("[Accessibility] UI tree extraction timed out.")
        return []
    except Exception as e:
        print(f"[Accessibility] Error: {e}")
        return []


def find_element(name_or_id: str, process_name: str = "") -> Optional[Dict]:
    """
    Find a specific UI element by name or AutomationId.
    Returns the element with its center coordinates for clicking.
    """
    elements = get_ui_tree(process_name)
    name_lower = name_or_id.lower()

    # Exact match first
    for el in elements:
        if (el.get("Name", "").lower() == name_lower or
                el.get("AutomationId", "").lower() == name_lower):
            return el

    # Partial match
    for el in elements:
        if (name_lower in el.get("Name", "").lower() or
                name_lower in el.get("AutomationId", "").lower()):
            return el

    return None


def get_clickable_elements(process_name: str = "") -> List[Dict]:
    """Get all clickable/interactive UI elements."""
    elements = get_ui_tree(process_name)
    clickable_types = [
        "ControlType.Button", "ControlType.Hyperlink", "ControlType.MenuItem",
        "ControlType.ListItem", "ControlType.TabItem", "ControlType.CheckBox",
        "ControlType.RadioButton", "ControlType.ComboBox", "ControlType.Edit",
        "ControlType.SplitButton"
    ]

    return [
        el for el in elements
        if el.get("ControlType") in clickable_types and el.get("IsEnabled", False)
    ]


def format_element_summary(elements: List[Dict], max_items: int = 30) -> str:
    """Format UI elements into a readable summary for the LLM."""
    if not elements:
        return "No UI elements found."

    lines = []
    for el in elements[:max_items]:
        name = el.get("Name", "")
        ctrl_type = el.get("ControlType", "").replace("ControlType.", "")
        cx = el.get("CenterX", 0)
        cy = el.get("CenterY", 0)

        if name:
            lines.append(f"  [{ctrl_type}] \"{name}\" at ({cx}, {cy})")

    return "\n".join(lines) if lines else "No named UI elements found."
