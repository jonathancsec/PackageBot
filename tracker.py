import os
import aiohttp

from dotenv import load_dotenv

load_dotenv()

SHIP24_API_KEY = os.getenv("SHIP24_API_KEY")

API_URL = "https://api.ship24.com/public/v1/trackers/track"


async def track_package(tracking_number):
    headers = {
        "Authorization": f"Bearer {SHIP24_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "trackingNumber": tracking_number
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            API_URL,
            headers=headers,
            json=data
        ) as response:

            text = await response.text()

            if response.status >= 400:
                raise Exception(
                    f"Ship24 returned HTTP {response.status}: {text}"
                )

            return await response.json()