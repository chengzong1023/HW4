#!/usr/bin/env python3
"""
Execute ARIA v2.0 notebook and generate required outputs
"""

import subprocess
import sys
import os
from pathlib import Path

def run_notebook():
    """Execute the ARIA_v2.ipynb notebook"""
    notebook_path = "ARIA_v2.ipynb"
    
    print(f"Executing {notebook_path}...")
    
    try:
        # Use nbconvert to execute the notebook
        result = subprocess.run([
            sys.executable, "-m", "jupyter", "nbconvert", 
            "--to", "notebook", 
            "--execute", 
            "--inplace",
            notebook_path
        ], capture_output=True, text=True, cwd=".")
        
        if result.returncode == 0:
            print("✅ Notebook executed successfully!")
            print(result.stdout)
        else:
            print("❌ Notebook execution failed!")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error executing notebook: {e}")
        return False
    
    # Check if output files were created
    output_files = ["terrain_risk_audit.json", "terrain_risk.geojson", "terrain_risk_map.png"]
    missing_files = []
    
    for file in output_files:
        if Path(file).exists():
            print(f"✅ {file} created successfully")
        else:
            print(f"❌ {file} not found")
            missing_files.append(file)
    
    if missing_files:
        print(f"Missing files: {missing_files}")
        return False
    
    return True

if __name__ == "__main__":
    success = run_notebook()
    sys.exit(0 if success else 1)
