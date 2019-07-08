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

class FileRecord:
	def __init__(self, cvr_id, path):
		self.cvr_id = cvr_id
		self.path = path
	
	def __repr__(self):
		return "%d: (%s)" % (self.cvr_id, self.path)

class BallotInfo:
	def __init__(self, cvr_id, style_string, express_vote, long_style_string=None, barcodes_string=None, failed=False, boxcount=0):
		self.cvr_id = cvr_id
		self.style_string = style_string
		self.express_vote = express_vote
		self.long_style_string = long_style_string
		self.barcodes_string = barcodes_string
		self.failed = failed
		self.boxcount = boxcount

	def __repr__(self):
		if self.failed:
			return "%d: FAILED" % (self.cvr_id)
		if self.express_vote:
			return "%d (expressvote): %s (%s --  %s)" % (self.cvr_id, self.style_string, self.long_style_string, self.barcodes_string)
		else:
			return "%d: %s (%d boxes)" % (self.cvr_id, self.style_string, self.boxcount)
		

def generate_files(filedir):
	files_in_dir = glob.glob(filedir + '/*-000.png')
	results_list = []
	for imgFile in files_in_dir:
		f = os.path.basename(imgFile)
		name = os.path.splitext(f)[0]
		results_list.append(FileRecord(int(name[:-5]), imgFile))
	return results_list

def generate_file_from_cvrid(cvr,png_dir, c):
	c.execute('select * from results where "Cast Vote Record" = {castrecord}'.format(castrecord=cvr))
	all_rows = c.fetchall()
	row = all_rows[0]
	f = FileRecord(cvr, png_dir + "/" + row["precinct"] + "/" + str(cvr) + "i-000.png")
	return([f])

