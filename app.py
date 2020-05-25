from slack import WebClient
from slackeventsapi import SlackEventAdapter
import os
import logging

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
slack_web_client = WebClient(SLACK_BOT_TOKEN)
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
slack_events_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, endpoint="/slack/events")

@slack_events_adapter.on("message")
def handle_message(event_data):
    message = event_data["event"]
    if message.get("bot_id") is None and message.get("subtype") is None:
        channel = message["channel"]
        text = "Instructions for using ReadingLinks: \n :one: "
        slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':text})

@slack_events_adapter.on("error")
def error_handler(err):
    print("ERROR: " + str(err))

slack_events_adapter.start(port=3000)