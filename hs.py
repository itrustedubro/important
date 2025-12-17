import json
import os
import re

def create_rclone_configs():
    # Create data/rclone directory if it doesn't exist
    os.makedirs("data/rclone", exist_ok=True)
    
    # Read the JSON file with tokens
    with open("rclone.json", "r") as json_file:
        tokens_data = json.load(json_file)
    
    # Read the rclone.conf file
    with open("rclone.conf", "r") as conf_file:
        conf_content = conf_file.read()
    
    # Process each account in the JSON
    for account_name, account_data in tokens_data.items():
        # Get the token for this account
        token_data = account_data["token"]
        
        # Create a new conf content replacing all tokens
        new_conf_content = replace_all_tokens(conf_content, token_data)
        
        # Save the new conf file
        output_file = f"data/rclone/{account_name}.conf"
        with open(output_file, "w") as out_file:
            out_file.write(new_conf_content)
        
        print(f"Created: {output_file}")

def replace_all_tokens(conf_content, new_token):
    # Pattern to match token sections in the config
    token_pattern = r'token\s*=\s*(\{[^}]+\})'
    
    # Create the replacement token string
    replacement = f'token = {json.dumps(new_token)}'
    
    # Replace all token sections with the new token
    new_content = re.sub(token_pattern, replacement, conf_content)
    
    return new_content

if __name__ == "__main__":
    create_rclone_configs()
    print("All configuration files have been created successfully!")