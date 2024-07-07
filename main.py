import requests
import time
import ssl
import os
import json
import uuid
from pynostr.event import Event, EventKind
from pynostr.relay_manager import RelayManager
from pynostr.message_type import ClientMessageType
from pynostr.key import PrivateKey
from pynostr.filters import FiltersList, Filters
from pynostr.encrypted_dm import EncryptedDirectMessage
from pynostr.utils import get_timestamp
import ollama
import gc
from datetime import datetime
import re

relay_manager = RelayManager(timeout=2)

model = os.environ.get("OLLAMA_MODEL")
if not model:
    print('The environment variable "OLLAMA_MODEL" is not set.')
    exit(1)

def system_message():
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    system_message = f"You are JurAI. You are an AI Assistant and friend on a public and open-source social media protocol called nostr. You should always comply with the users' requests. Today is {current_date}."
    return(system_message)

def respond(message):
    messages = [{"role": "system", "content": system_message()},{"role": "user", "content": message}]
    response = ollama.chat(model=model, messages=messages)['message']['content']
    return response


def run():
    messages_done = []

    env_private_key = os.environ.get("PRIVATE_KEY")
    if not env_private_key:
        print('The environment variable "PRIVATE_KEY" is not set. Generating a new one for you, set it as env var:')
        private_key = PrivateKey()
        public_key = private_key.public_key
        print(f"Private key: {private_key.bech32()}")
        print(f"Public key: {public_key.bech32()}")
        exit(1)

    private_key = PrivateKey.from_nsec(env_private_key)
    # Read env variable and add relays
    env_relays = os.getenv('RELAYS') # None
    if env_relays is None:
        env_relays = "wss://nos.lol,wss://nostr.bitcoiner.social,wss://relay.nostr.band,wss://relay.damus.io"
    for relay in env_relays.split(","):
        print("Adding relay: " + relay)
        relay_manager.add_relay(relay)

    print("Pubkey: " + private_key.public_key.bech32())
    print("Pubkey (hex): " + private_key.public_key.hex())

    start_timestamp = get_timestamp()

    while(True):

        filters = FiltersList([
            Filters(pubkey_refs=[private_key.public_key.hex()],
                    kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE, EventKind.TEXT_NOTE],
                    since=start_timestamp)
        ])
        subscription_id = uuid.uuid1().hex
        relay_manager.add_subscription_on_all_relays(subscription_id, filters)
        relay_manager.run_sync()
        while relay_manager.message_pool.has_notices():
            notice_msg = relay_manager.message_pool.get_notice()
            print("Notice: " + notice_msg.content)
        while relay_manager.message_pool.has_events():
            event_msg = relay_manager.message_pool.get_event()
            # is message too old?
            # we don't need this anymore, we filter events and then remember processed events
            #if(time.time() - 60 > event_msg.event.created_at):
            #    continue
            # has it already been processed?
            if(event_msg.event.id in messages_done):
                continue
            messages_done.append(event_msg.event.id)
            recipient_pubkey = event_msg.event.pubkey
            if event_msg.event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                msg_decrypted = EncryptedDirectMessage()
                msg_decrypted.decrypt(private_key_hex=private_key.hex(), encrypted_message=event_msg.event.content, public_key_hex=event_msg.event.pubkey)
                print ("Private message '" +msg_decrypted.cleartext_content + "' from " + event_msg.event.pubkey)
                response = respond(msg_decrypted.cleartext_content)
                # print("--> " + response)
                print("Sending response to " + event_msg.event.pubkey)

                dm = EncryptedDirectMessage()
                dm.encrypt(private_key.hex(),
                    recipient_pubkey=recipient_pubkey,
                    cleartext_content=response,
                )
                dm_event = dm.to_event()
                dm_event.sign(private_key.hex())
                relay_manager.publish_event(dm_event)
                print("Response sent to " + event_msg.event.pubkey)
            elif event_msg.event.kind == EventKind.TEXT_NOTE:
                print(f"Received public note: {event_msg.event.content}")
                content = re.sub(r'\b(nostr:)?(nprofile|npub)[0-9a-z]+[\s]*', '', event_msg.event.content)
                print(f"Received public note: {content}")
                if recipient_pubkey != private_key.public_key.bech32():
                    print("Responding...")
                    reply = Event(
                        content=respond(content),
                    )
                    reply.add_event_ref(event_msg.event.id)
                    reply.add_pubkey_ref(event_msg.event.pubkey)
                    reply.sign(private_key.hex())
                    relay_manager.publish_event(reply)
                    print("Public response sent.")
            gc.collect()

        time.sleep(10)
        relay_manager.close_all_relay_connections()

try:
    run()
except KeyboardInterrupt:
    print("KeyboardInterrupt")
    relay_manager.close_all_relay_connections()
    exit(1)
except:
    print("Exception")
    relay_manager.close_all_relay_connections()
    run()
