import json
import time
import uuid
import aiohttp
import asyncio
from pathlib import Path

import base64
import hashlib
import hmac

async def get_utkn(url_body: str, token: str, uid: str) -> str:
    signature = hmac.new(
        key=token.encode(),
        msg=url_body.encode(),
        digestmod=hashlib.sha1
    ).digest()
    return f"{uid}:{base64.b64encode(signature).decode()}"


async def fetch_data(url, headers, json):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=json) as response:
            response_json = await response.json()
            return response_json

async def refreshAuthToken(airtelConfig, did, authToken, token, uid):
    url = f'https://api.airtel.tv/v2/user/session/refreshAuthToken?appId={airtelConfig["appId"]}'

    trace_id = str(uuid.uuid4())
    request_init_time = str(int(time.time() * 1000))

    payload = {
        "token": authToken
    }

    ref_tok_post_json = json.dumps(payload)
    url_body = f"POST/v2/user/session/refreshAuthToken?appId={airtelConfig['appId']}" + ref_tok_post_json
    utkn = await get_utkn(url_body, token, uid)

    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'content-type': 'application/json',
        'origin': 'https://www.airtelxstream.in',
        'referer': 'https://www.airtelxstream.in/',
        'request-init-time': request_init_time,
        'user-agent': airtelConfig["userAgent"],
        
        'x-atv-ab': airtelConfig["experimentDetails"],
        'x-atv-did': f"{did}|{airtelConfig['dt']}|{airtelConfig['os']}|{airtelConfig['osVersion']}|{airtelConfig['appVersion']}|{airtelConfig['appVersionFull']}|{airtelConfig['platform']}|{airtelConfig['platform']}",
        'x-atv-traceid': trace_id,
        'x-atv-utkn': utkn
    }

    response_data = await fetch_data(url, headers, payload)
    return response_data
    


async def get_refreshAuthToken(airtelConfig):
    uid = airtelConfig["uid"]
    did = airtelConfig["did"]
    authToken = airtelConfig["authToken"]
    token = airtelConfig["token"]

    response_data = await refreshAuthToken(airtelConfig, did, authToken, token, uid)
    return response_data["token"]

async def main():
    config_path = Path("data/airtel_token.json")
    with open(config_path, "r") as f:
        airtel_config = json.load(f)
    
    new_token = await get_refreshAuthToken(airtel_config)
    print(f"New Token: {new_token}")
    
    # Update config with new token
    airtel_config["authToken"] = new_token
    with open(config_path, "w") as f:
        json.dump(airtel_config, f, indent=4)
    print("Config updated successfully!")

if __name__ == "__main__":
    asyncio.run(main())
