import os
import subprocess

# Get the current script's directory (same path as the shell and Python scripts)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Path to the shell script 'UpdatewithMB.sh'
sh_script_path = os.path.join(current_dir, 'UpdatewithMB.sh')

# Path to the Python script 'Sort_MoveMusicDownloads.py'
python_script_path = os.path.join(current_dir, 'Sort_MoveMusicDownloads.py')

# Function to run the shell script and wait for it to finish
def run_shell_script(script_path):
    try:
        # Execute the shell script and wait for it to complete
        subprocess.run(['bash', script_path], check=True)
        print(f"Successfully ran {script_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running {script_path}: {e}")

# Function to run the Python script
def run_python_script(script_path):
    try:
        # Execute the Python script and wait for it to complete
        subprocess.run(['python3', script_path], check=True)
        print(f"Successfully ran {script_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running {script_path}: {e}")

# Run the shell script first
run_shell_script(sh_script_path)

# After the shell script finishes, run the Python script
run_python_script(python_script_path)

