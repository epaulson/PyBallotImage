import json
import math
import glob
import os
import sys
import argparse
import sqlite3
import time
import csv
import itertools
from tqdm import tqdm
import multiprocessing

from ballot_image import ballot_image, contest_options, utils


# Lots of this is taken from https://eli.thegreenplace.net/2012/01/16/python-parallelizing-cpu-bound-tasks-with-multiprocessing
class Timer(object):
    def __init__(self, name=None):
        self.name = name

    def __enter__(self):
        self.tstart = time.time()

    def __exit__(self, type, value, traceback):
        if self.name:
            print('[%s]' % self.name, end=' ')
        print('Elapsed: %s' % (time.time() - self.tstart))

styleLookup = {
    "0,1,6,15,16,17,19,27,66": "style7.json",
    "00000000280000459009000011": "style7.json",
    "0,1,6,15,16,18,19,27,66": "style31.json",
    "00000002820002031873000011": "style31.json",
    "Ballot Style 31": "style31.json",
    "Ballot Style 7": "style7.json",
}


def basic_worker(targets, out_q):
	for t in targets:
		try:
			ballot = ballot_image.BallotImage(t.path)
			ballot.find_boxes()
		except Exception as e:
			#print(e)
			#print(t.path)
			b = utils.BallotInfo(t.cvr_id, style_string="Unknown", express_vote=False, failed=True) 
			out_q.put(b)
			continue
		if ballot.express_vote:
			b = utils.BallotInfo(t.cvr_id, ballot.detected_style[:-6], True, ballot.detected_style, ",".join([barcode for barcode in ballot.barcodes.keys()]))
		else:
			b = utils.BallotInfo(t.cvr_id, ballot.detected_style, False, boxcount=ballot.boxcount)
		out_q.put(b)
	
def basic_styles(targets, nprocs, output_file = None):
	ballots = []
	out_q = multiprocessing.Queue()
	procs = []
	chunksize = int(math.ceil(len(targets) / float(nprocs)))
	print("Items are %d" % (len(targets)))
	for i in range(nprocs):
		print("Chunk %d: starts at %d ends at %d" % (i, chunksize * i, chunksize * (i + 1)))	
	for i in range(nprocs):
		p = multiprocessing.Process(
			target=basic_worker,
			args=(targets[chunksize * i:chunksize * (i + 1)], out_q))
		procs.append(p)
		p.start()
	with tqdm(total=len(targets)) as pbar:
		for i in range(len(targets)):
			ballots.append(out_q.get())
			pbar.update(1)
	for p in procs:
		p.join()
	#print(len(ballots))
	#for b in ballots[:25]:
	#	print(b)
	#for b in ballots:
	#	if b.failed:
	#		print("Failed: %s" % (b))

	if output_file:
		with open(output_file, 'w', newline='') as csvfile:
			fieldnames = ['cvr_id', 'failed', 'style_string', 'express_vote', 'long_style_string', 'barcodes_string', "boxcount"]

			writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
			writer.writeheader()
			for b in ballots:
				writer.writerow({'cvr_id': b.cvr_id, 'failed': b.failed, 'style_string': b.style_string, 'express_vote': b.express_vote, 'long_style_string': b.long_style_string, 'barcodes_string': b.barcodes_string, 'boxcount': b.boxcount})
	else:
		for b in ballots:
			print(b)

def basic_styles_old(targets):
	ballots = []
	for t in tqdm(targets):
		ballot = ballot_image.BallotImage(t.path)
		ballot.find_boxes()
		#print("%s: %s" % (t.cvr_id, ballot.detected_style))
		if ballot.express_vote:
			ballots.append(BallotInfo(t.cvr_id, ballot.detected_style[:-6], True, ballot.detected_style, ",".join([barcode for barcode in ballot.barcodes.keys()])))

		else:
			ballots.append(BallotInfo(t.cvr_id, ballot.detected_style, False))

	for b in ballots:
		print(b)

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	group = parser.add_mutually_exclusive_group(required=True)	
	group.add_argument("--basic", action="store_true")
	parser.add_argument("--basic_output_file", default=None, help="Output CVS file for basic style classification")
	#group.add_argument("--score", action="store_true")
	parser.add_argument("--inputdir", help="Directory to scan",action="append", nargs="+")
	parser.add_argument("--cvrids", help="Cast Vote Records to process individually. Requires dbfile as well", type=int, action="append", nargs="+")
	parser.add_argument("--dbfile", default="test_data/records.db", help="sqlite3 database with CVRs")
	parser.add_argument("--pngdir", help="Top level directory for PNGs when using only CVRs")
	#parser.add_argument("--mismatches", help="File to store ballots that do not match ES&S 100 percent")
	#parser.add_argument("--expressvotes",  help="Output file for list of ballots that are expressvote images")
	#parser.add_argument("--overall",  help="File for overall scores")
	parser.add_argument("--nprocs", type=int, default=1, help="Number of workers to use")

	args = parser.parse_args()
	#overall_file= args.overall
	#mismatches_file = args.mismatches
	inputdirs = args.inputdir
	#expressvotes_file = args.expressvotes
	dbfile = args.dbfile
	cvrids = args.cvrids
	pngdir = args.pngdir
	nprocs = args.nprocs

	if cvrids:
		if dbfile is None:
			print("Error: specifying CVR IDs requires a SQLite database to be defined as well")
			exit(-1)

	if inputdirs:
		inputdirs = list(itertools.chain.from_iterable(inputdirs))
	if cvrids:
		cvrids = list(itertools.chain.from_iterable(cvrids))
	#print(inputdirs)
	if not inputdirs and not cvrids: 
		print("Must have at least some files to process!")
		exit(-1)

	conn = sqlite3.connect(dbfile)
	conn.row_factory = sqlite3.Row
	c = conn.cursor()
	files = []
	if inputdirs:
		for d in inputdirs:
			files.extend(utils.generate_files(d))
	if cvrids:
		for cvr in cvrids:
			files.extend(utils.generate_file_from_cvrid(cvr, pngdir, c))

	if args.basic:
		with Timer("Basic"):
			basic_styles(files, nprocs, args.basic_output_file)	

'''
overall = []
failed = []
expressvote = []
for imgFile in tqdm(files):
#for imgFile in files[0:10]:
	c.execute('select * from results where "Cast Vote Record" = {castrecord}'.format(castrecord=imgFile.cvr_id))
	all_rows = c.fetchall()
	row = all_rows[0]       
	
	try:
		ballot = ballot_image.BallotImage(imgFile.path, style=row["Ballot Style"], styleDir="/Users/epaulson/development/DaneCountyVotes/Fall2018General/ballot_styles")
		styleFile = styleLookup[row["Ballot Style"]] 
		cvr = contest_options.create_cvr("test_data/ballot_styles/" + styleFile, conn, imgFile.cvr_id)
		ballot.find_boxes()
		results = ballot.score(imgFile.cvr_id, cvr)
	except Exception as e:
		res = "%d: FAIL\n" % (imgFile.cvr_id)	
		failed.append(imgFile.cvr_id)
		overall.append(res)
		print(e)
		continue

	if results["expressVote"]==True:
		expressvote.append(imgFile.cvr_id)

	success = 0.0
	fail = 0.0
	for race in results["votes"]:
		details = race['details']
		if details['ESS'] != details['scored']:
			fail += 1.0
		else:
			success += 1.0
	if fail == 0.0:
		res = "%s: Success %f (%f match, %f misses)\n" % (imgFile.cvr_id, (success / (success+fail)), success, fail)	
		overall.append(res)
	if fail > 0.0:
		res = "%s: Partial %f (%f match, %f misses)\n" % (imgFile.cvr_id, (success / (success+fail)), success, fail)	
		overall.append(res)
		failed.append(imgFile.cvr_id)


print("Mismatches: (%d)" % (len(failed)))
for mismatch in failed:
	print(mismatch)

if overall_file:
	with open(overall_file, "w") as f:
		for x in overall:
			f.write(x)

if mismatches_file:
	with open(mismatches_file, "w") as f:
		for x in failed:
			f.write("%s\n" % str(x))

if expressvotes_file:
	with open(expressvotes_file, "w") as f:
		for x in expressvote:
			f.write("%s\n" % str(x))

'''
