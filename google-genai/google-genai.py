import argparse
import os
import re
import base64
import importlib.util
import subprocess
import sys
from datetime import datetime  # Added for timestamps

def backup_if_exists(filename):
    """
    If file exists, rename it to filename-YYYYMMDD-HHMMSS.ext
    """
    if os.path.exists(filename):
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{name}-{timestamp}{ext}"
        try:
            os.rename(filename, backup_name)
            print(f"[*] Backup created: {backup_name}")
        except OSError as e:
            print(f"[!] Could not backup {filename}: {e}")

def check_and_install_lib(package_name, import_name=None):
    """
    Checks if a library is installed. If not, installs it to the user directory.
    - package_name: The name used for 'pip install' (e.g., 'google-genai')
    - import_name: The name used for 'import' (e.g., 'google.genai')
    """
    if import_name is None:
        import_name = package_name

    # 1. Try to find the spec of the module
    spec = importlib.util.find_spec(import_name)
    
    if spec is None:
        print(f"[*] {import_name} not found. Starting installation...")
        
        try:
            # 2. Execute pip install to install in /usr (especially for pixL ;-)
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--prefix=/usr", package_name
            ])
            print(f"[+] {package_name} installed successfully.")
            
            # 3. Refresh sys.path to include the new installation immediately
            # We look for the site-packages folder in .local
            import site
            user_site = site.getusersitepackages()
            if user_site not in sys.path:
                sys.path.append(user_site)
                
            # 5. Verify the installation
            importlib.invalidate_caches()
            if importlib.util.find_spec(import_name):
                print(f"[!] {import_name} is now ready to use.")
                return True
            
        except subprocess.CalledProcessError as e:
            print(f"[-] Installation failed: {e}")
            return False
    else:
        print(f"[+] {import_name} is already installed.")
        return True

def main():
    
    # This example uses a log file and a few variables...
    # python3 google-genai.py \
    # --template "prompt_protonfix.txt" \
    # --api_key "$MY_API_KEY" \
    # --out_prefix "test" \
    # --vars Title="game of test" ID="test_game" \
    # --file_vars logs="logs/wine.log"
    
    # full example on one line : 
    # python3 google-genai.py --template "prompt_protonfix.txt" --api_key "$MY_API_KEY" --out_prefix "VT4" --vars game_title="Virtua Teniis 4" game_id="VT4" engine_version="GE-Proton9-27" renderer="dxvk 2.6"

    parser = argparse.ArgumentParser(description='Universal Gemini AI File & Media Generator')
    parser.add_argument('--template', required=True, help='Path to the .txt prompt template')
    parser.add_argument('--api_key', required=True, help='Gemini API Key')
    parser.add_argument('--model', default='gemini-2.5-flash-lite', help='Gemini model version')
    parser.add_argument('--vars', nargs='*', help='Text variables (Key=Value)')
    parser.add_argument('--file_vars', nargs='*', help='File variables (Key="path/to/file")')
    parser.add_argument('--out_prefix', default='output', help='Prefix for generated files')
    args = parser.parse_args()

    # 1. Load and Format Template
    if not os.path.exists(args.template): return print(f"Error: {args.template} not found.")
    with open(args.template, 'r') as f: prompt_content = f.read()

    var_dict = {}
    if args.vars:
        for item in args.vars:
            if '=' in item: k, v = item.split('=', 1); var_dict[k] = v

    if args.file_vars:
        for item in args.file_vars:
            if '=' in item:
                k, path = item.split('=', 1)
                if os.path.exists(path):
                    with open(path, 'r', errors='ignore') as f:
                        log_entry = f"\n--- FILE: {os.path.basename(path)} ---\n{f.read()}\n"
                        var_dict[k] = var_dict.get(k, "") + log_entry

    try:
        final_prompt = prompt_content.format(**var_dict)
    except KeyError as e: return print(f"Error: Missing variable {e}")

    #to work on unlock system (especilally for pixL)
    os.system("mount -o remount,rw /")
    
    # For the Gemini API, the package is 'google-genai' 
    # but the import test should be 'google.genai'
    if check_and_install_lib("google-genai", "google.genai"):
        from google import genai
        print("🚀 Script can now proceed with Gemini logic.")
    else:
        print("❌ Failed to set up environment.")
        sys.exit(1)

    # 2. Call Gemini API
    client = genai.Client(api_key=args.api_key)
    print(f"[*] Requesting generation for {args.out_prefix}...")
    
    try:
        # We use GenerateContent which can return multiple parts (text, code, images)
        response = client.models.generate_content(model=args.model, contents=final_prompt)
    except Exception as e: return print(f"API Error: {e}")

    # 3. Process Text Content (Code Blocks: bash, json, xml, py, etc.)
    full_text = response.text
    
    # Mapping Markdown languages to file extensions
    ext_map = {
        'python': 'py', 'py': 'py',
        'bash': 'sh', 'sh': 'sh', 'shell': 'sh',
        'json': 'json',
        'xml': 'xml',
        'yaml': 'yaml', 'yml': 'yml',
        'markdown': 'md', 'md': 'md'
    }

    # Find all blocks like ```python ... ```
    blocks = re.findall(r"```(\w+)\n(.*?)```", full_text, re.DOTALL)
    
    used_extensions = []
    for lang, code in blocks:
        ext = ext_map.get(lang.lower(), lang.lower())
        filename = f"{args.out_prefix}.{ext}"
        
        # Avoid overwriting if multiple blocks of same type exist
        if ext in used_extensions:
            filename = f"{args.out_prefix}_{len(used_extensions)}.{ext}"
        
        # --- BACKUP STEP ---
        backup_if_exists(filename)
        
        with open(filename, "w") as f:
            f.write(code.strip())
        print(f"[+] Saved Code Block: {filename}")
        used_extensions.append(ext)

    # 4. Save the "Clean" text (Instructions/Comments)
    clean_text = re.sub(r"```.*?```", "", full_text, flags=re.DOTALL).strip()
    # --- BACKUP STEP ---
    filename = f"{args.out_prefix}_README.txt"
    backup_if_exists(filename)
    with open(filename, "w") as f:
        f.write(clean_text)
    print(f"[+] Saved Info: {args.out_prefix}_README.txt")

    # 5. Process Binary/Image Content (Robust Version)
    if hasattr(response, 'candidates') and response.candidates:
        for i, candidate in enumerate(response.candidates):
            if hasattr(candidate.content, 'parts'):
                for j, part in enumerate(candidate.content.parts):
                    # Use getattr to safely check for inline_data
                    data_obj = getattr(part, 'inline_data', None)
                    
                    if data_obj and hasattr(data_obj, 'data'):
                        mime = getattr(data_obj, 'mime_type', 'application/octet-stream')
                        # Map mime types to extensions
                        ext = mime.split('/')[-1] if '/' in mime else 'bin'
                        
                        img_filename = f"{args.out_prefix}_{i}_{j}.{ext}"
                        with open(img_filename, "wb") as f:
                            f.write(data_obj.data)
                        print(f"[+] Saved Media: {img_filename}")

if __name__ == "__main__":
    main()