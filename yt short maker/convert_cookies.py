import json
import time
import sys
from pathlib import Path

def convert_json_to_netscape(json_path, netscape_path):
    try:
        with open(json_path, 'r') as f:
            cookies = json.load(f)

        if not isinstance(cookies, list):
            print("Error: JSON cookies should be a list.")
            return False

        with open(netscape_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This file was converted from JSON by yt2shorts\n\n")

            for c in cookies:
                domain = c.get('domain', '')
                if not domain:
                    continue

                # Netscape format: domain, flag, path, secure, expiration, name, value
                # flag: TRUE if domain starts with a dot
                flag = "TRUE" if domain.startswith('.') else "FALSE"
                path = c.get('path', '/')
                secure = "TRUE" if c.get('secure', False) else "FALSE"

                # expirationDate is usually in seconds
                expiration = c.get('expirationDate')
                if expiration is None:
                    expiration = int(time.time() + 31536000) # Default 1 year
                else:
                    expiration = int(expiration)

                name = c.get('name', '')
                value = c.get('value', '')

                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
        return True
    except Exception as e:
        print(f"Error converting cookies: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        # Default for this project
        success = convert_json_to_netscape('c.json', 'cookies.txt')
    else:
        success = convert_json_to_netscape(sys.argv[1], sys.argv[2])

    if success:
        print("Successfully converted cookies.")
        sys.exit(0)
    else:
        sys.exit(1)
