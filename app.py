from slack import WebClient
from slackeventsapi import SlackEventAdapter
import os
import logging
import pymongo

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
slack_web_client = WebClient(SLACK_BOT_TOKEN)
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
slack_events_adapter = SlackEventAdapter(SLACK_SIGNING_SECRET, endpoint="/slack/events")

ADMIN_NAME = os.environ["ADMIN_NAME"]
PASSWORD = os.environ["PASSWORD"]

uri="mongodb+srv://{}:{}@cluster0-bxwpr.mongodb.net/test?retryWrites=true&w=majority".format(ADMIN_NAME, PASSWORD)
cluster = pymongo.MongoClient(uri)
db = cluster["ReadingLinks"]
users = db["Users"]

instructions = '''Instructions for using ReadingLinks: \n
:one: type *add* followed by one link to add to your reading list \n
:two: type *view* to view your reading list \n
:three: type *remove* followed by an index in the reading list to remove a link \n
:four: tag ReadingLinks and teammates with a link to add to their reading lists'''

def add_link(client_id, channel, message_words):
	result = users.find_one({"_id":client_id})
	if len(message_words) < 2:
		error_message = "An *add* command must be followed by another argument."
		slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':error_message})
	elif users.count_documents({"_id":client_id}) == 0:
		users.insert_one({"_id": client_id, "list":[message_words[1]]})
		add_message = "{} has been added to your reading list.".format(message_words[1])
		slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':add_message})
	elif message_words[1] in result["list"]:
		old_link_message = "{} is already in your reading list.".format(message_words[1])
		slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':old_link_message})
	else:
		users.update_one({"_id":client_id}, {"$push":{"list":message_words[1]}})
		add_message = "{} has been added to your reading list.".format(message_words[1])
		slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':add_message})

@slack_events_adapter.on("message")
def handle_message(event_data):
    message = event_data["event"]
    text = message["text"]
    message_words = text.split()
    if message.get("bot_id") is None:
    	channel = message["channel"]
    	client_id = message["user"] + message["team"]
    	if message_words[0].lower() == "add":
    		add_link(client_id, channel, message_words)
    	elif message.get("subtype") is None:
	        slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':instructions})

@slack_events_adapter.on("error")
def error_handler(err):
    print("ERROR: " + str(err))

slack_events_adapter.start(port=3000)