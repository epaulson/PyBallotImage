import collections
import json

#ContestOption = collections.namedtuple('ContestOption', ('contest_option', 'pixel_pcts', 'x', 'y'))
class ContestOption:
	def __init__(self, contest_option, pixel_pcts=None, x=None, y=None, valid=True, xpixel=None, ypixel=None):
		self.contest_option = contest_option
		self.pixel_pcts = pixel_pcts
		self.x = x
		self.y = y
		self.valid = valid
		self.xpixel = xpixel
		self.ypixel = ypixel

	def __repr__(self):
		return "%s: pixelpct %s x %s y %s" % (self.contest_option, str(self.pixel_pcts), str(self.x), str(self.y))

	def __eq__(self, other):
		return self.contest_option == other.contest_option

class Contest:
	def __init__(self, contest_name, position=None, ess_scored=None, cv_scored=None):
		self.contest_name = contest_name
		self.position = position
		self.contest_options = collections.OrderedDict()
		self.contest_option_vote_ess = ess_scored
		self.contest_option_vote_scored = cv_scored

	def __repr__(self):
		if self.contest_option_vote_ess is not None:
			return 'Contest(%s) (ESS Vote: %s)' % (self.contest_name, self.contest_option_vote_ess)
		else:
			return 'Contest(%s)' % (self.contest_name)

	def __eq__(self, other):
		return (self.contest_name) == (other.contest_name)

	def add_contest_option(self, contest_option, pixel_pcts=None, x=None, y=None, valid=True):
		self.contest_options[contest_option] = ContestOption(contest_option=contest_option, pixel_pcts=pixel_pcts, x=x, y=y, valid=valid)

	def get_contest_option(self, contest_option):
		return self.contest_options[contest_option]

	def get_contest_options(self):
		if not len(self.contest_options):
			yield None
		choices = [choice for choicename, choice in self.contest_options.items()]
		for choice in sorted(choices, key = lambda option:option.y):
			yield choice

		
class CastVoteRecord:
	def __init__(self, cast_vote_record_id):
		self.cast_vote_record_id = cast_vote_record_id
		self.ballot_style = None
		self.ward = None
		self.express_vote = None
		self.contests = collections.OrderedDict()

	def add_contest(self, contest_info):
		self.contests[contest_info.contest_name] = contest_info

	def get_contest(self, contest_name):
		if contest_name in self.contests:
			return self.contests[contest_name]
		else:
			return None

	def get_contests(self):
		if not len(self.contests):
			return None
		else:
			for contest_name, contest in self.contests.items():
				yield contest

def create_cvr(style_file, dbconn, castrecord=None):

	cvr = CastVoteRecord(None)
	with open(style_file) as f:
		contests_data = json.load(f)

	
	row = None
	if dbconn:
		c = dbconn.cursor()
		c.execute('select * from results where "Cast Vote Record" = {castrecord}'.format(castrecord=castrecord))
		all_rows = c.fetchall()
		row = all_rows[0]
	
	for c in contests_data:
		if row:	
			contest = Contest(c['race'], position=c['position'], ess_scored=row[c['race']])	
		else:
			contest = Contest(c['race'], position=c['position'])	
		for option in c['race_details']:
			if 'x' not in c['race_details'][option] or "FIXME" in str(c['race_details'][option]['x']):
				contest.add_contest_option(option, pixel_pcts=None, x = 0, y = 0, valid=False)
			else:
				contest.add_contest_option(option, pixel_pcts=None, x = c['race_details'][option]['x'], y = c['race_details'][option]['y'], valid=True)
			
		cvr.add_contest(contest)
	return cvr
