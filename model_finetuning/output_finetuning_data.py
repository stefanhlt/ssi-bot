#!/usr/bin/env python3

from datetime import datetime

from peewee import fn

from db import (Comment as db_Comment, Submission as db_Submission)

import concurrent.futures

# a list of common bots to ignore the comments of. They will pollute the training data with junk.
# unless you want that, of course..
author_blacklist = ['automoderator', 'nfl_mod', 'totesmessenger', 'haikubot-1911', 'gfy_mirror', 'should_have_listened',
	'nice-scores', 'repliesnice', 'redditstreamable', 'twittertostreamable', 'streamablemirrors', 'originalpostsearcher',
	'b0trank', 'vredditdownloader', 'tweetposter', 'link-reply-bot', 'clickablelinkbot', 'i-am-dad-bot', 'GitHubPermalinkBot',
	'Freedom_Unit_Bot', 'LearnProgramming_Bot', 'CodeFormatHelperBot']

# A list of bad words. If these words are in the reddit comment, ignore that comment
# A good way to get the bot to behave nicely is to finetune it on healthy content in the first place
# There is usually always enough training data to comfortably filter out junk content like this
negative_keywords = []

text_removed = ['[removed]', '[deleted]']


def gather_comments_for_submission(sub):

	if text_matches_negative_keywords(sub.combined_text):
		# if the submission contains a negative keyword, 
		# ignore it so we don't train the bot on bad stuff
		print(f"{sub.id} contains negative keywords")
		return

	if any(s in sub.selftext for s in text_removed):
		# if the post has been edited or deleted it might contain [removed] or [deleted]
		# if it does, ignore this submission because we can't train on that
		print(f"blacklist selftext: {sub.selftext}")
		return

	if sub.author.lower() in author_blacklist:
		print(f"author blacklist {sub.author}")
		return

	# pick out all of the comments in this submission(topic) ordered by the highest score, descending
	top_rated_comments = list(db_Comment.select().where((db_Comment.link_id == f't3_{sub.id}') &
		(fn.Lower(db_Comment.author.not_in(author_blacklist)))).order_by(db_Comment.score.desc()))

	for tr_comment in top_rated_comments:
		# Here, we will start to create a string representation of the reddit submission, with all comments in a thread
		# in chronological order

		print(f"starting top rated comments loop {sub.id}")

		# this is the end of the training string.. all text will be prepended to this
		if tr_comment.submission().is_self:
			# is_self parameter means it is a selftext submission
			text_gen_string = "<|eoss|>"
		else:
			# Otherwise it is a link submission (ie just a title and URL)
			text_gen_string = "<|eols|>"

		ancestor = tr_comment
		comments_counted = 0

		# From the top rated comment, we'll loop back up the comment thread until
		# we reach the submission
		# Then we have the submission text and comment text all in the correct reply
		# order that represents how humans have a conversation
		while ancestor is not None:

			if (ancestor.author.lower() in author_blacklist or
				ancestor.author.lower().endswith('bot')):
				# is probably a bot account, break the loop
				break

			if isinstance(ancestor, db_Comment):
				if any(s in ancestor.body for s in text_removed):
					print("blacklist text... breaking")
					break

				record_string = f"<|sor|>{ancestor.body}<|eor|>"

				# build the text_gen_string up backwards
				text_gen_string = record_string + text_gen_string
				comments_counted += 1

			elif isinstance(ancestor, db_Submission):

				if ancestor.is_self:
					# is_self parameter means it is a selftext submission
					record_string = f"<|soss|><|sot|>{ancestor.title}<|eot|><|sost|>{ancestor.selftext}<|eost|>"
				else:
				# if there's no selftext then it's just a linkpost.
					record_string = f"<|sols|><|sot|>{ancestor.title}<|eot|><|sol|>{ancestor.url}<|eol|>"

				text_gen_string = record_string + text_gen_string
				break

			# get the next comment up in the thread and compile the text for that, too.
			ancestor = ancestor.parent()

		if text_gen_string.startswith("<|sols") or text_gen_string.startswith('<|soss') and comments_counted > 0:
			# sols/soss is in the thread so we reached the submission and counted at least one comment
			# that's sufficient to add into the training output data.
			return text_gen_string


def text_matches_negative_keywords(text):
	return any(s in text for s in negative_keywords)


def main():

	all_submissions = []

	training_subreddits = []
	bot_name = "training_output"

	# all submissions ordered by date
	all_submissions = list(db_Submission.select().
		where((fn.Lower(db_Submission.subreddit).in_([s.lower() for s in training_subreddits])) &
				(fn.Lower(db_Submission.author).not_in([a.lower() for a in author_blacklist]))
				& (db_Submission.score > 1))
		.order_by(db_Submission.created_utc.asc()))

	print(len(all_submissions))

	counter = 0

	# file name for the output text file
	date_string = datetime.today().strftime('%d%m%y_%H%M')
	global filename
	filename = f'{bot_name}_{date_string}.txt'

	# use concurrent futures (multiprocessing) to speed up the output
	with concurrent.futures.ProcessPoolExecutor() as executor:
		for sub, output_text_gen_string in zip(all_submissions, executor.map(gather_comments_for_submission, all_submissions)):
			counter += 1
			if output_text_gen_string:
				with open(filename, 'a', encoding='utf-8') as fd:
					fd.write(f'{output_text_gen_string}' + '\n')
			print(f'subs counted: {counter}. {round(counter/len(all_submissions), 2)}')


if __name__ == '__main__':
	main()
