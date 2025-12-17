import binascii
import base64

def read_key_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            key_data = f.read()
            
        print(f"Key length: {len(key_data)} bytes")
        
        # Display as hex
        hex_key = binascii.hexlify(key_data).decode()
        print("\nHex format:")
        print(hex_key)
        
        # Display as base64
        base64_key = base64.b64encode(key_data).decode()
        print("\nBase64 format:")
        print(base64_key)
        
        # Display as bytes
        print("\nRaw bytes:")
        print([hex(b) for b in key_data])
        
    except Exception as e:
        print(f"Error reading key: {e}")

if __name__ == "__main__":
    read_key_file("serve.key") 