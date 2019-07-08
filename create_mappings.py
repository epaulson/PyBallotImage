import sqlite3
import pandas as pd
import numpy as np
from tqdm import tqdm
import sys
from collections import OrderedDict 
import argparse
import json
import pprint

# from https://stackoverflow.com/questions/6190331/can-i-do-an-ordered-default-dict-in-python
class OrderedDefaultListDict(OrderedDict): #name according to default
	def __missing__(self, key):
		self[key] = value = [] #change to whatever default you want
		return value

parser = argparse.ArgumentParser()
parser.add_argument("database_schema", help="File with database columns")
#parser.add_argument("expressvote_data", help="File with decoded expressvotes")
parser.add_argument("dbfile", help="Database to use")
parser.add_argument("--stylefile", help="file of ballotstyles to process")
parser.add_argument("--outputdir", help="directory to store output")
parser.add_argument("--ballotstyle", help="Ward to process")
args = parser.parse_args()


lines = None
with open(args.database_schema) as f:
        lines = f.readlines()
        lines = [line.strip()[:-6] for line in lines]
        lines = [line[1:-1] for line in lines]
        #lines = [line.strip().replace('"', r'\"') for line in lines]


styles = []
if args.stylefile:
	with open(args.stylefile) as f:
		styles = f.readlines()
		styles = [l.strip() for l in styles]

if args.stylefile and args.ballotstyle:
	exit("Can't have both a stylefile and a ballotstyle")

if args.ballotstyle:
	styles = [args.ballotstyle]


conn = sqlite3.connect(args.dbfile)

query = "select \"%s\", count(*) from results group by \"%s\""

races = []
for race in tqdm(lines):
	#print(query % (race))
	candidates = pd.read_sql(query % (race, race), conn)
	#print(candidates)
	#print(race)
	options = []	
	for c in candidates[candidates.columns[0]].values.tolist():
		if c is not None and c != "overvote" and c != "undervote":
			options.append(c)
	races.append((race, options))	

	#with open('../web/wd9barcodes.txt') as f:
	#with open(args.expressvote_data) as f:
	#    lines = f.readlines()
	#    lines = [l.strip() for l in lines]

expressvotes_query = "select cvr_id,barcodes_string from full where express_vote = \"True\" and  \"Ballot Style\" = \"%s\""
for ballotstyle in styles:
	
	cursor = conn.cursor()
	expressvotes = pd.read_sql(expressvotes_query % (ballotstyle), conn)
	print(expressvotes)

	mappings = {}
	for index, row in expressvotes.iterrows():
		res = row['barcodes_string'].split(',')
		mappings[row['cvr_id']] = res

	#print(mappings)


	for_query = "select \"Cast Vote Record\" from results where \"%s\" = \"%s\" and \"Ballot Style\" = \"%s\" order by random()"
	against_query = "select \"Cast Vote Record\" from results where \"%s\" != \"%s\" and \"Ballot Style\" = \"%s\""
	any_query = "select count(*) from results where \"%s\" is not null and \"Ballot Style\" = \"%s\""

	ballot_positions = OrderedDefaultListDict()

	# races at this point is an array of tuples
	# first element is the race name, second element is all possible candidates (minus over and undervote)
	# e.g.
	# ('Justice of the Supreme Court', ['Brian Hagedorn', 'Lisa Neubauer', 'write-in:'])
	# ('Court of Appeals Judge, District IV', ['Jennifer Nashold', 'write-in:'])
	# ('Circuit Court Judge, Branch 16', ['Rhonda L. Lanford', 'write-in:'])
	for r in races:
		race = r[0]
		cursor=conn.cursor()
		# first, for this race, let's make sure that there is at least one vote for it somewhere, e.g. on a ballot style used
		# only in madison don't look for a sun prairie mayor vote
		cursor.execute(any_query % (race, ballotstyle))
		count = cursor.fetchone()
		if count[0] == 0:
			continue

		# OK, this is a race that has votes in thhis ballot style
		# now, for each potential candidate, find all the ballots where someone voted for this candidate
		# and where people didn't vote for this candidate
		#
		# We're trying to figure out the X/Y coordinates of a candidate, e.g. where is Brian Hagedorn on this ballot
		# But we don't know which X/Y position is associated with which race
		# We know that it must be one of the positions on the ballots of the people who voted for hagedorn, and everyone
		# who voted for hagedorn is guaranteed to have that as one of their choices, so take
		# the positions that appear on EVERY ballot of people who voted for hagedorn, e.g. the intersection
		#
		for candidate in r[1]:
			for_candidates = pd.read_sql(for_query % (race, candidate, ballotstyle), conn)
			against_candidates = pd.read_sql(against_query % (race, candidate, ballotstyle), conn)

			everyone_else = against_candidates['Cast Vote Record'].values.tolist()

			candidate_barcodes = None
			for cvr in for_candidates.values.tolist():
				if "%s" % (str(cvr[0])) in mappings:
					if candidate_barcodes:
						candidate_barcodes.intersection_update(set(mappings[str(cvr[0])]))
					else:
						candidate_barcodes = set(mappings[str(cvr[0])])

			if candidate_barcodes is None:
				ballot_positions[race].append((candidate, None))
				continue

		# Furthermore, we know that for anyone who voted for Neubauer or wrote someone in, NONE of the X/Y positions
		# on their ballot could possibly be Hagedorn, so eliminate all X/Y pairs that occur on ANY of the ballots who
		# voted for neubauer or wrote someone in i.e. the set difference

			mismatch_barcodes = set()
			for ballot in everyone_else:
				if str(ballot) in mappings:
					mismatch_barcodes.update(set(mappings[str(ballot)]))

			print(candidate)
			print("Candidate barcodes: %s " % (candidate_barcodes))
			print("Mismatched barcode: %s" % (mismatch_barcodes))
			a = candidate_barcodes - mismatch_barcodes
			print("Diff: %s\n\n" % (a)) 
			#print("%s: %s" % (candidate, a))
			ballot_positions[race].append((candidate, a))

	#foo = [('"Justice of the Supreme Court"', [('Brian Hagedorn', {'0118'}), ('Lisa Neubauer', {'0119'}), ('write-in:', None)]), ('"Court of Appeals Judge, District IV"', [('Jennifer Nashold', {'0133', '0128', '0124', '0146'}), ('write-in:', None)]), ('"Circuit Court Judge, Branch 16"', [('Rhonda L. Lanford', {'0133', '0128', '0124', '0146'}), ('write-in:', None)]), ('"County Supervisor, District 36 (1-year term) District 36"', [('Melissa Ratcliff', {'0133', '0128', '0124', '0146'}), ('write-in:', None)]), ('"Town Board Chairperson T Cottage Grove"', [('Kris Hampton', {'0138'}), ('write-in:', {'0139', '0143'})]), ('"Town Board Supervisor 1 T Cottage Grove"', [('Mike Fonger', {'0142'}), ('write-in:', {'0139', '0143'})]), ('"Town Board Supervisor 2 T Cottage Grove"', [('Steven Anders', {'0133', '0128', '0124', '0146'}), ('write-in:', None)]), ('"Municipal Judge T Cottage Grove"', [('April Hammond-Archibald', {'0909'}), ('Sheryl K. Albers-Anders', {'0910'}), ('write-in:', None)]), ('"Deerfield Community School District Board Member"', [('Lisa Sigurslid', set()), ('Tom Bush', {'0916'}), ('write-in:', None)]), ('"Unnamed: 286"', [('Lisa Sigurslid', set()), ('write-in:', {'0918'})])]
	#styles = foo

	#print(ballot_positions)
	#for x in ballot_positions:
	#	print("x: + " + x)

	results_struct = []
	for position, (race, candidates) in enumerate(ballot_positions.items(), 1):
		#print(position)
		#print("Race: " + race)
		#print("Candidates: " + str(candidates))
		contest = {}
		contest['race'] = race
		contest['position'] = position
		details = {}
		#print(styles[position])
		for choice in candidates:
			#print("Choice: " + str(choice))
			#print("Zero: " + choice[0])
			#print("One: " + str(choice[1]))
			choice_name = choice[0]
			
			choice_xy = {}
			if choice[1] is None:
				choice_xy["x"] = "FIXME"
				choice_xy["y"] = "FIXME"
			else:
				candidates = list(choice[1])
				if len(candidates) == 1:
					try:	
						choice_xy["x"] = (int(candidates[0][0:2]))
						choice_xy["y"] = (int(candidates[0][2:4]))
					except ValueError as e:
						choice_xy["x"] = "FIXME"
						choice_xy["y"] = "FIXME"
				if len(candidates) > 1:
					choice_xy["x"] = "FIXME " + str(candidates)
					choice_xy["y"] = "FIXME"
					
			details[choice_name] = choice_xy
		contest['race_details'] = details
		results_struct.append(contest)

	print(json.dumps(results_struct,  indent=4))

	if args.outputdir:
		filename = ballotstyle + "_style.json"
		filename = filename.replace(" ", "_")
		with open(args.outputdir + "/" + filename, "w") as f:
			json.dump(results_struct, f, indent=4)
