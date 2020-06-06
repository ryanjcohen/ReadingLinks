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

def add_link(client_id, message, channel=None, user=None):
	'''
		Adds link(s) contained in an input message payload to the reading list of the user
		represented by client_id. Then sends a message from the bot to the channel specified 
		by the input channel parameter with content based on the suceess of adding the 
		link(s) to the user's reading list.

		Args:
			client_id: concatentation of a user's user id and the team_id of the slack 
				team; equal to the id of the entry for the user's reading list in 
				the database.
			message: the message payload containing data about links to potentially
				be added to a user's reading list.
			channel: the id of the slack channel to which the bot should report the
				success of adding the links to the user's reading list.
			user: the user id of the user whose reading list the links potentially
				contained in the message payload should be added to.
	'''
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
			# A reading list for the user does not exist in the database.
			users.insert_one({"_id":client_id, "list":links})
		else:
			for link in links:
				# Add links that are not already in the user's reading list.
				if link not in result["list"]:
					users.update_one({"_id":client_id}, {"$push":{"list":link}})
		if len(links)==1:
			message = ":white_check_mark: The following link is now in your reading list: {}".format(links[0])
		else:
			message = ":white_check_mark: The following links are now in your reading list: "
			for link in links:
				message = message + link + " "
		if channel is None:
			# Identify channel for direct messaging successly added links to the user.
			new_convo = slack_web_client.conversations_open(users=user)
			channel = new_convo['channel']['id']
	if channel is not None:
		slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text': message})

def view_links(client_id, channel):
	'''
		Creates a string containing a numbered list of the links in the reading list of 
		the user represented by client_id and sends the string as a message from the 
		bot to the slack channel with an id equal to the input channel paramter.

		Args:
			client_id: concatentation of a user's user id and the team_id of the slack 
				team; equal to the id of the entry for the user's reading list in 
				the database.
			channel: the id of the slack channel to which the bot should post the string
				containing the reading list of the user indicated by client id.
	'''
	result = users.find_one({"_id":client_id})
	message = ""
	if result is None:
		message = "Your reading list is empty."
	else:
		link_num = 1
		for link in result["list"]:
			message = message + ":link: *{}:* ".format(link_num) + link + "\n"
			link_num += 1
	slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text': message})

def convertable_to_int(string):
	'''
		Determines whether an input string can be converted to an int.

		Args:
			string: input string being checked for whether it can be converted to an int.

		Returns:
			a boolean indicating whether or not the input parameter string can be converted
			to an int.
	'''
	try: 
		int(string)
		return True
	except ValueError:
		return False

def remove_link(client_id, channel, message_words):
	'''
		Removes the link from the reading list of the user represeted by client_id whose 
		number is equivalent to that specified by the second word in the string message_words.
		Then sends a message from the bot to the channel specified by the input channel parameter 
		with content based on the success of removing the specified the link from the user's 
		reading list.

		Args:
			client_id: concatentation of a user's user id and the team_id of the slack 
				team; equal to the id of the entry for the user's reading list in 
				the database.
			channel: the id of the slack channel to which the bot should post the string
				containing the reading list of the user indicated by client id.
			message_words: the text of a message to the bot where the second word is equivalent
				to the number for the link to be removed from the specified user's reading list.
	'''
	result = users.find_one({"_id":client_id})
	message = ""
	if results is None:
		message = "You cannot remove a link from an empty reading list!"
	elif len(message_words)==1 or not convertable_to_int(message_words[1]):
		message = "You must follow the *remove* command by a number."
	else:
		link_idx = int(message_words[1]) - 1
		if link_idx > len(result["list"]) - 1:
			message = "You don't have a link in your reading list that is numbered {}!".format(link_idx+1)
		else:
			link = result["list"][link_idx]
			# Remove string with index equal to link in the user's list.
			users.update_one({"_id":client_id}, {"$unset":{"list.{}".format(link_idx): 1}})
			users.update_one({"_id":client_id}, {"$pull":{"list": None}})
			message = ":white_check_mark: {} has been removed from your reading list.".format(link)
	slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text': message})

def clear_list(client_id, channel):
	'''
		Clears the reading list of the user represented by the input client_id by deleting
		the document with an id equal to client_id from the database. Then sends a message
		from the bot to the channel specified by the input parameter channel with content
		based on the success of clearing the reading list.

		Args:
			client_id: concatentation of a user's user id and the team_id of the slack 
				team; equal to the id of the entry for the user's reading list in 
				the database.
			channel: the id of the slack channel to which the bot should post the string
				containing the reading list of the user indicated by client id.
	'''
	message = ""
	if users.count_documents({"_id":client_id})==0:
		message = "Your reading list was already empty!"
	else:
		users.delete_one({"_id": client_id})
		message = ":white_check_mark: Your reading list has been cleared."
	slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text': message})

@slack_events_adapter.on("message")
def handle_message(event_data):
	'''
		Initiates a slack bot response based on the input event_data, the payload received
		when a message event occurs, meaning that a message has been sent to a channel in 
		the work space.

		Args:
			event_data: the payload event received when a message event occurs.
	'''
	message = event_data["event"]
	if message.get("bot_id") is None and message.get("subtype") is None:
		text = message["text"]
		message_words = text.split()
		channel = message["channel"]
		client_id = message["user"] + message["team"]
		if message_words[0].lower() == "add":
			add_link(client_id, message, channel=channel, )
		elif message_words[0].lower() == "view":
			view_links(client_id, channel)
		elif message_words[0].lower() == "remove":
			remove_link(client_id, channel, message_words)
		elif message_words[0].lower() == "clear":
			clear_list(client_id, channel)
		else:
			slack_web_client.api_call("chat.postMessage", json={'channel':channel, 'text':instructions})

@slack_events_adapter.on("app_mention")
def handle_mention(event_data):
	'''
		Produces a slack bot response based on the input event_data, the payload received
		when an app_mention event occurs, meaning that the bot has been tagged in a message
		in a channel that it is a member of. This response consists of adding the
		link(s) in the message tagging the bot to the reading lists of the user(s) also
		tagged in the message and posting a response by the bot to the message indicating
		the success of this action.

		Args:
			event_data: the payload event received when an app_message event occurs.
	'''
	data = event_data['event']['blocks'][0]['elements'][0]['elements']
	ts = event_data['event']['ts']
	team = event_data['team_id']
	user_ids = []
	links = []
	# Add the id's of the tagged users and the links in the message in which the bot was tagged 
	# to the arrays user_ids and links, respectively.
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
			# Extract user's name within the workspace.
			name = user_info['profile']['real_name']
			if name != 'ReadingLinks':
				names.append(name)
				client_id = user + team
				result = users.find_one({"_id":client_id})
				if result is None:
					users.insert_one({"_id": client_id, "list":links})
				else:
					# Insert links not currently in user's reading list into the list.
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
	'''
		Initiates a slack bot response based on the input data, the payload received
		when a reaction_added event occurs, meaning that a user has added a reaction
		to a message within a channel of which the bot is a member. Response consists
		of adding links in the message that the user reacted to to the user's reading
		list if the reaction was a link emoji.

		Args:
			data: the payload event received when a reaction_added event occurs.
	'''
	# Check if the emoji the user reacted to a message with is a link emoji.
	if data['event']['reaction'] == 'link':
		ts = data['event']['item']['ts']
		channel = data['event']['item']['channel']
		# Retrieve the message that the user reacted to.
		retrieved_message = slack_web_client.conversations_history(channel=channel, latest=ts, 
			limit=1, inclusive=True)
		user = data['event']['user']
		client_id = user + data['team_id']
		add_link(client_id, retrieved_message['messages'][0],user=user)	

@slack_events_adapter.on("error")
def error_handler(err):
	'''
		Prints the input err when an error event occurs.
	'''
	print("ERROR: " + str(err))

slack_events_adapter.start(port=3000)