import sys
import json
import sqlite3
import os
from collections import defaultdict
import argparse
import itertools

from flask import Flask, render_template, make_response, url_for
from flask_bootstrap import Bootstrap
from flask import jsonify
from flask import g

#import numpy as np
#import cv2
#from imutils import contours
#import imutils

from ballot_image import ballot_image, contest_options, utils

app = Flask(__name__)
Bootstrap(app)
app.config['BOOTSTRAP_SERVE_LOCAL'] = True
app.config['SERVER_NAME'] = 'localhost:5000'


# from http://flask.pocoo.org/docs/1.0/patterns/sqlite3/
#DATABASE = '/Users/epaulson/development/DaneCountyVotes/Fall2018General/original/records.db'
#IMAGE_PATH = '/Users/epaulson/development/DaneCountyVotes/test_data/images/'
#STYLE_DIR = "/Users/epaulson/development/DaneCountyVotes/Fall2018General/ballot_styles"
DATABASE = './test_data/records.db'
IMAGE_PATH = './test_data/images/'
STYLE_DIR = "./test_data/ballot_styles"

styleLookup = {
    "0,1,6,15,16,17,19,27,66": "style7.json",
    "00000000280000459009000011": "style7.json",
    "0,1,6,15,16,18,19,27,66": "style31.json",
    "00000002820002031873000011": "style31.json",
    "Ballot Style 31": "style31.json",
    "Ballot Style 7": "style7.json",
}

def get_db():
	db = getattr(g, '_database', None)
	if db is None:
		db = g._database = sqlite3.connect(app.config['DATABASE'])
		db.row_factory = sqlite3.Row
	return db

def query_db(query, args=(), one=False):
	cur = get_db().execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv

@app.teardown_appcontext
def close_connection(exception):
	db = getattr(g, '_database', None)
	if db is not None:
		db.close()



@app.after_request
def after_request(response):
	response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
	response.headers["Expires"] = 0
	response.headers["Pragma"] = "no-cache"
	return response

@app.route('/')
def index():
    return render_template('index.html')

# help from https://chrisalbon.com/python/data_wrangling/break_list_into_chunks_of_equal_size/
def chunks(l, n):
    # For item i in a range that is a length of l,
	for i in range(0, len(l), n):
		# Create an index range for l of n items:
		yield l[i:i+n]

@app.route('/images/')
def getImages():
	ballots = [x.cvr_id for x in app.config['FILES']]
	ballot_chunks = list(chunks(ballots, 500))
	data = defaultdict(list)
	for chunk in ballot_chunks:
		query = "select Precinct, \"Ballot Style\", \"Cast Vote Record\" from results where \"Cast Vote Record\" in ({seq})".format(seq=','.join(['?']*len(chunk)))
		ballot_meta = query_db(query, chunk)
		if app.config["BY_STYLES"]:
			display_key = 'Ballot Style'
		else:
			display_key = "Precinct"
		#print(display_key)
		for b in ballot_meta:
			#print(b)
			data[b[display_key]].append(str(b["Cast Vote Record"]))
	'''
	with open(app.config['dataset']) as f:
		data = defaultdict(list)
		ballots = []
		for ballot in f.readlines():
			ballot = ballot.strip()
			ballots.append(int(ballot))
		query = "select Precinct, \"Cast Vote Record\" from results where \"Cast Vote Record\" in ({seq})".format(seq=','.join(['?']*len(ballots)))
		ballot_meta = query_db(query, ballots)
		for b in ballot_meta:
			data[b["Precinct"]].append(str(b["Cast Vote Record"]))

	'''
	results = []
	for group_by_key, ballots in data.items():
		d = {}
		d["text"] = group_by_key
		d["selectable"] = False
		d["state"] = {"expanded": False}
		d["nodes"] = [{"text": x} for x in ballots]
		results.append(d)	
	return jsonify(results)

def common(imgFile):
	#ballot_meta = query_db('select Precinct, "Ballot Style" from results where "Cast Vote Record" = ?', [int(imgFile[:-1])], one=True)
	ballot_meta = query_db('select Precinct, "Ballot Style" from results where "Cast Vote Record" = ?', [int(imgFile)], one=True)

	cvr = None
	if app.config["STYLEDIR"]:
		styleFile = ballot_meta["Ballot Style"] + "_style.json"
		styleFile = styleFile.replace(" ", "_") 
		styleFile = app.config["STYLEDIR"] + "/" + styleFile
		if os.path.isfile(styleFile):
			cvr = contest_options.create_cvr(styleFile, get_db(), int(imgFile))

	ballot = ballot_image.BallotImage(app.config['PNGDIR'] + "/" + ballot_meta["Precinct"] + "/" + imgFile + 'i-000.png', style=ballot_meta["Ballot Style"], styleDir=STYLE_DIR, cvr=cvr)

	return ballot

@app.route('/image/<imgFile>/scored_image')
def scored_image(imgFile):
	ballot = common(imgFile)
	
	ballot.find_boxes()
	results = ballot.score()
	if ballot.express_vote:
		buffer = ballot.raw_as_png()
	else:
		buffer = ballot.scored_as_png()
	
	response = make_response(buffer.tobytes())
	response.headers['Content-Type'] = 'image/png'
	return response

@app.route('/image/<imgFile>/dewarped_image')
def dewarped_image(imgFile):
	ballot = common(imgFile)
	
	ballot.find_boxes()
	buffer = ballot.dewarped_as_png()
	
	response = make_response(buffer.tobytes())
	response.headers['Content-Type'] = 'image/png'
	return response

@app.route('/image/<imgFile>/scored_json')
def score_json(imgFile):
	ballot  = common(imgFile)
	ballot.find_boxes()
	#results = ballot.score(imgFile, cvr)
	results = ballot.score()

	return jsonify(results)

@app.route('/image/<imgFile>/raw')
def imageRaw(imgFile):
	ballot = common(imgFile)

	buffer = ballot.raw_as_png()
	
	response = make_response(buffer.tobytes())
	response.headers['Content-Type'] = 'image/png'
	return response

@app.route('/image/<imgFile>/debug/<target>')
def imageCandidateBlocks(imgFile, target):
	ballot = common(imgFile)

	try:
		buffer = ballot.find_boxes()
	except Exception as e:
		#print("Ignoring exception %s" % (e))
		pass
	buffer = ballot.debug_image(target)
	response = make_response(buffer.tobytes())
	response.headers['Content-Type'] = 'image/png'
	return response


if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	group = parser.add_mutually_exclusive_group(required=True)      
	group.add_argument("--basic", action="store_true")
	parser.add_argument("--by-styles", action="store_true")
	parser.add_argument("--inputdir", help="Directory to scan",action="append", nargs="+")
	parser.add_argument("--cvrids", help="Cast Vote Records to process individually. Requires dbfile as well", type=int, action="append", nargs="+")
	parser.add_argument("--cvrfile", help="File of CVR IDs. Requires dbfile as well", action="append", nargs="+")
	parser.add_argument("--dbfile", default="test_data/records.db", help="sqlite3 database with CVRs")
	parser.add_argument("--pngdir", help="Top level directory for PNGs when using only CVRs")
	parser.add_argument("--styledir", help="Top level directory for ballot style files")

	args = parser.parse_args()
	inputdirs = args.inputdir
	dbfile = args.dbfile
	cvrids = args.cvrids
	cvrfiles = args.cvrfile
	pngdir = args.pngdir
	styledir = args.styledir
	by_styles = args.by_styles 

	if cvrids:
		if dbfile is None:
			print("Error: specifying CVR IDs requires a SQLite database to be defined as well")
			exit(-1)

	if inputdirs:
		inputdirs = list(itertools.chain.from_iterable(inputdirs))
	if cvrids:
		cvrids = list(itertools.chain.from_iterable(cvrids))
	if cvrfiles:
		cvrfiles = list(itertools.chain.from_iterable(cvrfiles))

	files = []
	if inputdirs:
		for d in inputdirs:
			files.extend(utils.generate_files(d))

	conn = sqlite3.connect(dbfile)
	conn.row_factory = sqlite3.Row
	c = conn.cursor()


	if cvrfiles:
		for fname in cvrfiles:
			with open(fname) as f:
				ids = f.readlines()
				ids = [id.strip() for id in ids]	
				if not cvrids:
					cvrids = []
					cvrids.extend(ids)
				else:
					cvrids.extend(ids)
					
	if cvrids:
		for cvr in cvrids:
			files.extend(utils.generate_file_from_cvrid(cvr, pngdir, c))

	conn.close()


	app.config['DATABASE']=dbfile
	app.config['FILES']= files
	app.config['STYLEDIR'] = styledir
	app.config['BY_STYLES'] = by_styles

	#app.config['dataset'] = 'test_data/sample100-wd9.txt'
	app.config['PNGDIR'] = pngdir
	app.run()
