from slack import WebClient
from slackeventsapi import SlackEventAdapter
import os
import logging
import pymongo
from urllib.parse import urlparse

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
:three: type *remove* followed by the number of a link in the reading list to remove it \n
:four: type *clear* to remove all links from your reading list \n
:five: tag ReadingLinks and teammates with a link to add to their reading lists'''

def add_link(client_id, channel, message, emoji_reaction):
	links = []
	data = message['blocks'][0]['elements'][0]['elements']
	message = ""
	for element in data:
		if element['type'] == 'link' and element['url'] not in links:
			links.append(element['url'])
	if len(links) == 0:
		message = "An *add* command must be followed by one or more links."
	else:
		result = users.find_one({"_id":client_id})
		if result == None:
			users.insert_one({"_id":client_id, "list":links})
		else:
			for link in links:
				if link not in result["list"]:
					users.update_one({"_id":client_id}, {"$push":{"list":link}})
		if len(links)==1:
			message = "The following link is now in your reading list: {}".format(links[0])
		else:
			message = "The following links are now in your reading list: "
			for link in links:
				message = message + link + " "
	if not emoji_reaction:
		post_message(channel,message)

def view_links(client_id, channel):
	result = users.find_one({"_id":client_id})
	if users.count_documents({"_id":client_id}) == 0:
		empty_message = "Your reading list is empty."
		post_message(channel,empty_message)
	else:
		reading_list = ""
		link_num = 1
		for link in result["list"]:
			reading_list = reading_list + ":link: *{}:* ".format(link_num) + link + "\n"
			link_num += 1
		post_message(channel,reading_list)

def convertable_to_int(string):
	try: 
		int(string)
		return True
	except ValueError:
		return False

def remove_link(client_id, channel, message_words):
	result = users.find_one({"_id":client_id})
	if users.count_documents({"_id":client_id}) == 0:
		empty_message = "You cannot remove a link from an empty reading list!"
		post_message(channel, empty_message)
	elif len(message_words)==1 or not convertable_to_int(message_words[1]):
		non_int_message = "You must follow the *remove* command by a number."
		post_message(channel, non_int_message)
	else:
		link_idx = int(message_words[1]) - 1
		if link_idx > len(result["list"]) - 1:
			invalid_index = "You don't have a link in your reading list that is numbered {}!".format(link_idx+1)
			post_message(channel, invalid_index)
		else:
			link = result["list"][link_idx]
			users.update({"_id":client_id}, {"$unset":{"list.{}".format(link_idx): 1}})
			users.update({"_id":client_id}, {"$pull":{"list": None}})
			removed_link = ":white_check_mark: {} has been removed from your reading list.".format(link)
			post_message(channel, removed_link)

def clear_list(client_id, channel):
	if users.count_documents({"_id":client_id})==0:
		empty_message = "Your reading list was already empty!"
		post_message(channel, empty_message)
	else:
		users.delete_one({"_id": client_id})
		cleared_message = ":white_check_mark: Your reading list has been cleared."
		post_message(channel, cleared_message)

def post_message(channel, message):
	slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text': message})

@slack_events_adapter.on("message")
def handle_message(event_data):
	message = event_data["event"]
	if message.get("bot_id") is None and message.get("subtype") is None:
		text = message["text"]
		message_words = text.split()
		channel = message["channel"]
		client_id = message["user"] + message["team"]
		if message_words[0].lower() == "add":
			add_link(client_id, channel, message, False)
		elif message_words[0].lower() == "view":
			view_links(client_id, channel)
		elif message_words[0].lower() == "remove":
			remove_link(client_id, channel, message_words)
		elif message_words[0].lower() == "clear":
			clear_list(client_id, channel)
		elif message.get("subtype") is None:
			post_message(channel,instructions)
	#TODO: handle subtype message_changed?

@slack_events_adapter.on("app_mention")
def handle_mention(event_data):
	data = event_data['event']['blocks'][0]['elements'][0]['elements']
	ts = event_data['event']['ts']
	team = event_data['team_id']
	user_ids = []
	links = []
	for element in data:
		if element['type']=='user':
			user_ids.append(element['user_id'])
		elif element['type']=='link' and element['url'] not in links:
			links.append(element['url'])
	channel = event_data['event']['channel']
	if len(links)==0:
		no_links = "Message does not contain a valid link."
		slack_web_client.chat_postMessage(channel=channel,text=no_links,thread_ts=ts)
	elif len(user_ids)==1:
		no_users = "Message does not indicate which user reading lists to add link to."
		slack_web_client.chat_postMessage(channel=channel,text=no_users,thread_ts=ts)
	else:
		names = []
		for user in user_ids:
			user_info = slack_web_client.users_profile_get(user=user)
			name = user_info['profile']['real_name']
			if name != 'ReadingLinks':
				names.append(name)
				client_id = user + team
				if users.count_documents({"_id":client_id}) == 0:
					users.insert_one({"_id": client_id, "list":links})
				else:
					result = users.find_one({"_id":client_id})
					for link in links:
						if link not in result['list']:
							users.update_one({"_id":client_id}, {"$push":{"list":link}})
		added_message = ""
		if len(links)>1 and len(names)>1:
			added_message = "The above links are now in the reading lists of:"
		elif len(links)>1 and len(names)==1:
			added_message = "The above links are now in the reading list of:"
		elif len(links)==1 and len(names)>1:
			added_message = "The above link is now in the reading lists of:"
		elif len(links)==1 and len(names)==1:
			added_message = "The above link is now in the reading list of:"
		for name in names:
			added_message = added_message + " @" + name
		slack_web_client.chat_postMessage(channel=channel,text=added_message,thread_ts=ts)

@slack_events_adapter.on("reaction_added")
def handle_reaction(data):
	if data['event']['reaction'] == 'link':
		ts = data['event']['item']['ts']
		channel = data['event']['item']['channel']
		retrieved_messages = slack_web_client.conversations_history(channel=channel, latest=ts, 
			limit=1, inclusive=True)
		client_id = data['event']['user'] + data['team_id']
		add_link(client_id, channel, retrieved_messages['messages'][0],True)	

@slack_events_adapter.on("error")
def error_handler(err):
    print("ERROR: " + str(err))

slack_events_adapter.start(port=3000)