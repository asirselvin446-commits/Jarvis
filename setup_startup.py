import os
import sys
import getpass

def setup_startup():
    username = getpass.getuser()
    startup_path = f"C:\\Users\\{username}\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"
    
    jarvis_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable
    # Use python.exe because pythonw.exe has sys.stdout=None which crashes our print statements.
    # The '0' flag in VBScript already hides the console window.
    pythonw_exe = python_exe

    vbs_path = os.path.join(startup_path, "JarvisStartup.vbs")
    
    vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{jarvis_dir}"
WshShell.Run Chr(34) & "{pythonw_exe}" & Chr(34) & " " & Chr(34) & "main.py" & Chr(34), 0
Set WshShell = Nothing
"""
    
    with open(vbs_path, "w") as f:
        f.write(vbs_content)
        
    print(f"Startup script created at: {vbs_path}")
    print("J.A.R.V.I.S. will now start automatically when you log in.")

if __name__ == "__main__":
    setup_startup()
