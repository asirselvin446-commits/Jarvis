"""Full Master OS test suite for all Jarvis local & autonomous operations."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.os_kernel import OSKernel

kernel = OSKernel()

print("=" * 60)
print("J.A.R.V.I.S. AI OS — MASTER SYSTEM INTEGRITY TEST")
print("=" * 60)

# 1. Registered tools count
tool_names = list(kernel.tool_manager.tools.keys())
print(f"\n[+] Total Registered Tools ({len(tool_names)}):")
for name in sorted(tool_names):
    print(f"    - {name}")

tests = [
    ("play_youtube", "play shape of you on youtube"),
    ("play_spotify", "play starboy on spotify"),
    ("whatsapp_send_message", "send message to Chandru on WhatsApp saying I will be there in ten minutes"),
    ("get_system_status", "what is my battery, CPU, and RAM status?"),
    ("clipboard_read", "read my clipboard"),
    ("execute_terminal", "run terminal command dir"),
    ("open_application", "open notepad"),
    ("open_folder", "open downloads folder"),
    ("set_volume", "set volume to 50"),
    ("set_brightness", "set brightness to 80"),
]

print("\n" + "=" * 60)
print("TESTING PLANNER TOOL SELECTION ACROSS ALL DOMAINS:")
print("=" * 60)

all_passed = True
for expected_tool, prompt in tests:
    plan = kernel.planner.plan_and_select_tools(prompt, "", kernel.tool_schemas)
    print(f"\nPrompt: '{prompt}'")
    if plan['type'] == 'tools':
        selected = plan['tool_calls'][0]['function']['name']
        args = plan['tool_calls'][0]['function']['arguments']
        match = "MATCH" if selected == expected_tool else f"MISMATCH (expected {expected_tool})"
        if selected != expected_tool:
            all_passed = False
        print(f"  -> Tool: {selected} [{match}]")
        print(f"  -> Args: {args}")
    else:
        print(f"  -> Response: {plan.get('content', '')[:100]}")
        all_passed = False

print("\n" + "=" * 60)
if all_passed:
    print("SUCCESS: ALL MASTER SYSTEM INTEGRITY TESTS PASSED!")
else:
    print("WARNING: SOME TESTS DID NOT MATCH EXPECTED TOOLS")
print("=" * 60)
