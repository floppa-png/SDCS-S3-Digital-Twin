import subprocess
import time
import sys
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="SDCS Digital Twin Runner")
    parser.add_argument("--hitl", action="store_true", help="Launch with Hardware-In-The-Loop (Pluto) mode enabled")
    args = parser.parse_args()

    print("============================================================")
    print("   SDCS Digital Twin — Modulation Optimization Platform    ")
    print("============================================================")
    
    python_exe = os.path.join("python_ml", "venv", "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable

    env = os.environ.copy()
    p_bridge = None
    
    if args.hitl:
        print("\n[Mode] Pluto SDR Hardware-In-The-Loop enabled (--hitl)")
        radioconda_python = r"C:\Users\vmj07\radioconda\python.exe"
        bridge_py = radioconda_python if os.path.exists(radioconda_python) else python_exe
        print(f" -> Launching Pluto Native Bridge ({bridge_py})...")
        p_bridge = subprocess.Popen([bridge_py, "pluto_native_bridge.py"])
        env["SDCS_MODE"] = "pluto"
        env["PLUTO_BRIDGE_MANAGED"] = "1"
        
        # Wait until Pluto bridge XML-RPC is online and ready
        import socket
        t_wait = time.time()
        bridge_ready = False
        while time.time() - t_wait < 8.0:
            if p_bridge.poll() is not None:
                print(f"[Error] Pluto native bridge exited prematurely (code {p_bridge.poll()}).")
                break
            try:
                with socket.create_connection(('127.0.0.1', 8090), timeout=0.3):
                    bridge_ready = True
                    break
            except Exception:
                time.sleep(0.3)
        if bridge_ready:
            print(" -> Pluto hardware bridge is online and ready!")
    else:
        print("\n[Mode] High-Fidelity Simulation Mode (Default)")

    print("[Ready] Starting Web Dashboard & Telemetry Engine (port 5000)...")
    p_dash = subprocess.Popen([python_exe, "dashboard/app.py"], env=env)
    
    print("\n -> Open Web Interface: http://127.0.0.1:5000")
    print("Press Ctrl+C to terminate the system.\n")
    
    try:
        while p_dash.poll() is None:
            time.sleep(0.5)
        exit_code = p_dash.poll()
        if exit_code and exit_code != 0:
            print(f"\n[Warning] Dashboard server exited unexpectedly with return code {exit_code}.")
    except KeyboardInterrupt:
        print("\nCtrl+C detected! Terminating Digital Twin System...")
    finally:
        for p, name in [(p_dash, "Dashboard"), (p_bridge, "Pluto Bridge")]:
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    p.kill()
                print(f"{name} cleanly stopped.")

if __name__ == "__main__":
    main()
