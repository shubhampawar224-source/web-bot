import os
import asyncio
from dotenv import load_dotenv
from livekit import api

# .env file load karein
load_dotenv()

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

def create_token():
    if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        print("❌ Error: .env file mein API Key ya Secret nahi mila!")
        return

    token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
        .with_identity("user-frontend") \
        .with_name("Human User") \
        .with_grants(api.VideoGrants(
            room_join=True,
            room="my-room",  # <-- Room ka naam same hona chahiye
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))

    jwt_token = token.to_jwt()
    print("\n✅ Yeh raha aapka Token (Niche se copy karein):\n")
    print(jwt_token)
    print("\n")

if __name__ == "__main__":
    create_token()