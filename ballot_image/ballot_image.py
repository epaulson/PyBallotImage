import math
import json
import random

import numpy as np
import cv2

import imutils
from imutils import contours, perspective
from pyzbar.pyzbar import decode

from . import contest_options


class NoLinesException(Exception):
	pass


#https://stackoverflow.com/questions/1939228/constructing-a-python-set-from-a-numpy-matrix
from hashlib import sha1
from numpy import ndarray, uint8, array

class HashableNdarray(ndarray):
    def __hash__(self):
        if not hasattr(hasattr, '__hash'):
            self.__hash = int(sha1(self.view(uint8)).hexdigest(), 16)
        return self.__hash

    def __eq__(self, other):
        if not isinstance(other, HashableNdarray):
            return super(HashableNdarray, self).__eq__(other)
        return super(HashableNdarray, self).__eq__(super(HashableNdarray, other)).all()

#
# A little helper function to find corners
# the input are 4 arrays of contours, which are the timing boxes
# we found on the edges of the ballot image
# The corners are the contours that are in two arrays
# 
# TODO: rewrite this to find contours that intersect two lines
# rather than doing this as a set intersection, cuz that can go
# wrong from time to time.
#
def find_corners(top, bottom, left, right):
	top_set = set()
	bottom_set = set()
	left_set = set()
	right_set = set()
	for c in top:
		top_set.add(c.view(HashableNdarray))
	for c in bottom:
		bottom_set.add(c.view(HashableNdarray))
	for c in left:
		left_set.add(c.view(HashableNdarray))
	for c in right:
		right_set.add(c.view(HashableNdarray))
		
	top_left = set.intersection(top_set, left_set)
	top_right = set.intersection(top_set, right_set)
	bottom_left = set.intersection(bottom_set, left_set)
	bottom_right = set.intersection(bottom_set, right_set)


	#print("Top left: %d" % len(top_left))
	#print("Top right: %d" % len(top_right))
	#print("Bottom left: %d" % len(bottom_left))
	#print("Bottom right: %d" % len(bottom_right))
	top_left_box = top_left.pop().view(ndarray)
	top_right_box = top_right.pop().view(ndarray)
	bottom_left_box = bottom_left.pop().view(ndarray)
	bottom_right_box = bottom_right.pop().view(ndarray)

	return top_left_box, top_right_box, bottom_left_box, bottom_right_box

def find_center(p):
	p_m = cv2.moments(p)
	#print(p_m)
	p_x = int(p_m["m10"] / p_m["m00"]) 
	p_y = int(p_m["m01"] / p_m["m00"])
	return([p_x, p_y])

#https://peteris.rocks/blog/extrapolate-lines-with-numpy-polyfit/
# give a bunch of line segments, fit them to a single line
# use the line to calculate new x/y points for the endpoints
def find_line_endpoints(lines, vertical=False):
	x = []
	y = []

	for line in lines:
		(x1,y1,x2,y2) = line[0]
		x += [x1, x2]
		y += [y1, y2]

	# FIXME - remove hardcoded consts
	xmin = 0
	xmax = 1700
	if vertical:
		temp = x
		x = y
		y = temp
		xmax = 2800

	z = np.polyfit(x, y, 1)
	f = np.poly1d(z)

	#xmin = min(x)
	#xmax = max(x)

	x_new = np.array([xmin, xmax])
	y_new = f(x_new).astype(int)
	points_new = list(zip(x_new, y_new))
	
	px, py = points_new[0]
	cx, cy = points_new[-1]

	if vertical:
		return((py, px), (cy, cx))
	else:
		return(points_new[0], points_new[-1])

#
# This takes an image that is mostly only timing track rectangles
# so we're going to use a hough transform to try to combine them into lines
# 
# The Hough xform gives us a whole bunch of line segments, which go in the right direction but might
# only cover part of a side, but overall it gives us a whole bunch of line segments that all overlap
# and combined they'd all cover the whole length, so we use them as inputs and fit a single line to them
# all and return endpoints for that line
#
def find_lines(image):
		minLineLength =1 
		maxLineGap = 200 

		# The OpenCV tutorial is wrong about hough transforms:
		# https://stackoverflow.com/questions/35609719/opencv-houghlinesp-parameters
		gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
		#lines = cv2.HoughLinesP(gray,rho = 1,theta = 1*np.pi/180,threshold = 400,minLineLength = 300,maxLineGap = 150)
		lines = cv2.HoughLinesP(gray,rho = .5,theta = 1*np.pi/180,threshold = 400,minLineLength = 1000,maxLineGap = 350)
		if lines is None:
			# probably barcode ballot...
			raise NoLinesException
		
		top = []
		bottom = []
		left = []
		right = []
		debug_image = np.zeros(image.shape, dtype = "uint8")
		debug_image2 = np.zeros(image.shape, dtype = "uint8")
		for line in lines:
			(x1,y1,x2,y2) = line[0]
			cv2.line(debug_image2,(x1, y1), (x2, y2), (255,0,0),3)
			
		for line in lines:
			(x1,y1,x2,y2) = line[0]
			# is this a horizontal line
			if abs(x2-x1) > 500:
				if ((y1 + y2) / 2.0) > 1000:
					bottom.append(line)
				else:
					top.append(line)
			else:
				if ((x1 + x2) / 2.0) > 500:
					right.append(line)
				else:
					left.append(line)

		top_start, top_stop = find_line_endpoints(top)
		cv2.line(debug_image,top_start, top_stop, (0,255,0),3)

		bottom_start, bottom_stop = find_line_endpoints(bottom)
		cv2.line(debug_image,bottom_start, bottom_stop, (255,0,0),3)

		left_start, left_stop = find_line_endpoints(left, vertical=True)
		cv2.line(debug_image,left_start, left_stop, (0,0,255),3)

		right_start, right_stop = find_line_endpoints(right, vertical=True)
		cv2.line(debug_image,right_start, right_stop, (0,255,255),3)

		return debug_image, top_start, top_stop, bottom_start, bottom_stop, left_start, left_stop, right_start, right_stop

def find_candidate_blocks(image, target_shape, tight=True, debug=False):
	results = cv2.findContours(image.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
	debug_image = np.zeros(target_shape, dtype = "uint8")

	cnts = results[1]

	if tight:
		thin_ar_min = 0.55
		thin_ar_max = 0.78
		thin_area_min = 250.0
		thin_area_max = 375.0

		full_ar_min = 1.2
		full_ar_max = 1.69
		full_area_min = 575.0
		full_area_max = 750.0

		min_bcr = 0.75
		max_bcr = 1.05
	else:
		thin_ar_min = 0.40
		thin_ar_max = 1.1
		thin_area_min = 100.0
		thin_area_max = 500.0

		full_ar_min = 1.02
		full_ar_max = 1.69
		full_area_min = 500.0
		full_area_max = 910.0

		min_bcr = 0.65
		max_bcr = 1.15


	# First, let's find potential boxes. We're going to find bounding boxes
	# with aspect ratios between 1.2 and 1.6 and that are at least 1200 pixels
	# in area, and we'll keep that list in cont_outlines
	# and then sort them top-to-bottom

	candidate_timing_blocks = []
	for c in cnts:
		c =  cv2.approxPolyDP(c,0.04*cv2.arcLength(c,True),True)
		if len(c) < 3:
			continue
		#cv2.drawContours(debug_image, [c], -1, (0,0,255), 1)
		(x, y, w, h) = cv2.boundingRect(c)
		boundingRectArea = w * h	
		contourArea = cv2.contourArea(c)
		boundToContourRatio = contourArea / float(boundingRectArea)
		# ar is aspect ratio
		ar = w / float(h)
		if boundToContourRatio >= min_bcr and boundToContourRatio < max_bcr: 
			#cv2.drawContours(debug_image, [c], -1, (255,0,255), -1)
			# temporary debugging - only look at boxes on the lower left
			#if y > 1000 and y < 1500 and x < 300:
			#if y > 2500 and x > 900 and x < 1400:
			#if y < 300 and x > 1400:
			if y > 300 and y < 400 and x > 1400:
			#if y < 300 and x > 500 and x < 1400:
				(cx,cy) = find_center(c)
				#rnd_y = (cx % 50) * 50
				rnd_y = random.randint(130,2400)
				rnd_x = random.randint(100,900)
				rnd_r = random.randint(0,255)
				rnd_g = random.randint(0,255)
				rnd_b = random.randint(0,255)
				cv2.putText(debug_image, "%f %f %f %d %d" % (boundToContourRatio, contourArea, ar, w, h), (rnd_x, rnd_y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (rnd_b, rnd_g, rnd_r), 2)
				cv2.line(debug_image, (cx, cy), (rnd_x,rnd_y), (rnd_b, rnd_g, rnd_r),2)

		# there are two types of boxes we're interested in - the fat ones
		# that make up the top and bottom rows and are used to mark "ballot style"
		# ane the thinner ones that are just timing track positions on the left and right
		# columns
		if boundToContourRatio >= min_bcr and boundToContourRatio < max_bcr: 
			if (  ( (thin_area_min <= contourArea <= thin_area_max) and (thin_ar_min <= ar <= thin_ar_max))
					or
					( (full_area_min <= contourArea <= full_area_max) and (full_ar_min <= ar <= full_area_max) )	
				):
				candidate_timing_blocks.append(c)
				cv2.drawContours(debug_image, [c], -1, (0,0,255), -1)
			else:
				pass

	# debug_image is our scratchpad image that we can show our work
	# for example, we annotate some contours with area/aspect ratios to see
	# what we want to include in the results
	return candidate_timing_blocks, debug_image

def dewarp(image, topleft, topright, bottomleft, bottomright):

	#print("Shape before: %s" % (str(image.shape)))
	image = cv2.copyMakeBorder(image, 200,200,200,200,cv2.BORDER_CONSTANT, value=[255,255,255])
	#print("Shape after: %s" % (str(image.shape)))

	trans_const = 200

	(topleft_x, topleft_y) = find_center(topleft)
	(topright_x, topright_y) = find_center(topright)
	(bottomleft_x, bottomleft_y) = find_center(bottomleft)
	(bottomright_x, bottomright_y) = find_center(bottomright)

	topleft_x += trans_const
	topleft_y += trans_const
	bottomleft_x += trans_const
	bottomleft_y += trans_const
	
	topright_x += trans_const
	topright_y += trans_const
	bottomright_x += trans_const
	bottomright_y += trans_const
	L = [[topleft_x, topleft_y], [topright_x, topright_y], [bottomright_x, bottomright_y], [bottomleft_x, bottomleft_y]]
	ctr = np.array(L).reshape((-1,1,2)).astype(np.int32)
	#print(ctr)
	#cv2.drawContours(image,[ctr],0,(0,255,255),1)

    # http://answers.opencv.org/question/44580/can-i-resize-a-contour/
	temp_M = cv2.moments(ctr)
	temp_Cx = int(temp_M["m10"] / temp_M["m00"])
	temp_Cy = int(temp_M["m01"] / temp_M["m00"])
	temp_center = np.array([temp_Cx, temp_Cy])
	ctr = ctr - temp_center
	#print("After translation")
	#print(ctr)
	ctr = ctr * 1.2
	#print("After scale")
	#print(ctr)
	ctr = ctr + temp_center
	#print("After untranslation")
	ctr = ctr.astype(np.int32)
	#print(ctr)
	#cv2.drawContours(image,[ctr],0,(255,0,0),1)

	image = perspective.four_point_transform(image, ctr.reshape(4,2))
	return image



class BallotImage:


	def styleLoad(self):
		styleFile = styleLookup[self.style] 
		with open(self.styledir + "/" + styleFile) as f:
 			self.races  = json.load(f)
		
	def __init__(self, front_path, style=None, styleDir=None, cvr=None):
		self.front_path = front_path
		self.styledir = styleDir
		self.express_vote = False
		self.style = style
		self.cvr = cvr
		self.detected_style = "Unknown"
		if(self.front_path):
			self._raw_image = cv2.imread(self.front_path)
			self.image = self._raw_image.copy()
		else:
			raise ValueError

		self._gray = self._raw_image
		#print("Size: %s " % (str(self._gray.shape)))
		self._blurred = cv2.GaussianBlur(self._gray, (5, 5), 0)
		self.coltopx = None
		self.coltopy = None
		self.colbotx = None
		self.colboty = None

		self.rowleftx = None
		self.rowlefty = None
		self.rowrightx = None
		self.rowrighty = None


	def get_style(self):
		"""Returns the ballot style detected in the image. This is the number in the upper right corner"""
		return self.style

	def get_top_right_corner(self):
		"""return first 10% of image"""
		#return self._gray[:int(self._gray.shape[1] *.1), 1500:].copy()
		#print(self._gray.shape)
		#print((self._gray.shape[0] * .9))
		return self._gray[:int(self._gray.shape[0] *.05), int(self._gray.shape[1] *.85):].copy()

	def get_raw_image(self):
		"""Returns the original OpenCV image of the entire ballot
		The caller is responsible for making a copy if they don't want to modify the original
		"""
		return self._raw_image 

	def get_row_registration(self):
		pass

	def raw_as_png(self):
		raw = cv2.cvtColor(self._raw_image.copy(), cv2.COLOR_BGR2GRAY)
		retval, buffer = cv2.imencode('.png', raw)
		#retval, buffer = cv2.imencode('.png', self.corrected)
		return buffer


	def dewarped_as_png(self):
		retval, buffer = cv2.imencode('.png', self.image)
		#retval, buffer = cv2.imencode('.png', self.image)
		#retval, buffer = cv2.imencode('.png', self.corrected)
		return buffer

	def scored_as_png(self):
		retval, buffer = cv2.imencode('.png', self.scored_image)
		#retval, buffer = cv2.imencode('.png', self.image)
		#retval, buffer = cv2.imencode('.png', self.corrected)
		return buffer


	def debug_image(self, target):
		if target == "pass1_candidate_blocks":
			retval, buffer = cv2.imencode('.png', self.pass1_candidate_blocks)
		if target == "pass2_candidate_blocks":
			retval, buffer = cv2.imencode('.png', self.pass2_candidate_blocks)

		if target == "pass1_candidate_blocks_tight":
			retval, buffer = cv2.imencode('.png', self.pass1_candidate_blocks_tight)
		if target == "pass2_candidate_blocks_tight":
			retval, buffer = cv2.imencode('.png', self.pass2_candidate_blocks_tight)

		if target == "pass1_line_image":
			retval, buffer = cv2.imencode('.png', self.pass1_line_image)
		if target == "pass2_line_image":
			retval, buffer = cv2.imencode('.png', self.pass2_line_image)

		if target == "pass1_timing_track_contours_image":
			retval, buffer = cv2.imencode('.png', self.pass1_contour_image)
		if target == "pass2_timing_track_contours_image":
			retval, buffer = cv2.imencode('.png', self.pass2_contour_image)
		if target == "pass1_contour_image2":
			retval, buffer = cv2.imencode('.png', self.pass2_contour_image1)
		if target == "pass2_contour_image2":
			retval, buffer = cv2.imencode('.png', self.pass2_contour_image2)

		if target == "pass1_inverse_image":
			retval, buffer = cv2.imencode('.png', self.pass1_inverse_image)
		if target == "pass2_inverse_image":
			retval, buffer = cv2.imencode('.png', self.pass2_inverse_image)

		#if target == "pass1_debug_template_match":
		#	retval, buffer = cv2.imencode('.png', self.pass1_debug_template_match)
		#if target == "pass2_debug_template_match":
		#	retval, buffer = cv2.imencode('.png', self.pass2_debug_template_match)

		if target == "pass1_corners_image":
			retval, buffer = cv2.imencode('.png', self.pass1_corners_image)
		if target == "pass2_corners_image":
			retval, buffer = cv2.imencode('.png', self.pass2_corners_image)

		if target == "pass2_xformed_raw_image":
			retval, buffer = cv2.imencode('.png', self.pass2_xformed_raw_image)

		if target == "style_image":
			retval, buffer = cv2.imencode('.png', self.style_image)


		#retval, buffer = cv2.imencode('.png', self.corrected)
		return buffer
		

	def _find_boxes(self, image, debug=False, warped=False):
		side = cv2.cvtColor(image.copy(), cv2.COLOR_BGR2GRAY)
		side = cv2.GaussianBlur(side, (5, 5), 0)
		thresh = cv2.threshold(side, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
		
		thresh = cv2.erode(thresh, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=3)
		thresh = cv2.dilate(thresh, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=3)

		#kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
		#thresh = cv2.morphologyEx(thresh_1, cv2.MORPH_CLOSE, kernel)

		if warped:
			self.pass2_inverse_image = thresh
		else:
			self.pass1_inverse_image = thresh
		candidate_timing_blocks, candidate_blocks_debug_image = find_candidate_blocks(thresh,image.shape, tight=True)
		if warped:
			self.pass2_candidate_blocks_tight = candidate_blocks_debug_image
		else:
			self.pass1_candidate_blocks_tight = candidate_blocks_debug_image

		#orig_img = image
		candidate_blocks_image = np.zeros(image.shape, dtype = "uint8")
		for c in candidate_timing_blocks:
			cv2.drawContours(candidate_blocks_image, [c], -1, (0,255,255),-1)
		if warped:
			self.pass2_contour_image2 = candidate_blocks_image
		else:
			self.pass1_contour_image2 = candidate_blocks_image


		# OK, we have a blank image except for things we think _might_ be blocks from the timing track. We were conservative in what
		# we considered as candidates, because it's ok to miss a few right now - we are looking to find a good line that overlays these
		# canddiate blocks
		try:
			line_debug_image, top_start, top_stop, bottom_start, bottom_stop, left_start, left_stop, right_start, right_stop = find_lines(candidate_blocks_image)
		except NoLinesException:
			#self.image = orig_img
			raise NoLinesException
		except Exception as e:
			print("Something has gone wrong in detect lines: %s" % (e), flush=True)
			raise 

		if warped:
			self.pass2_line_image = line_debug_image
		else:
			self.pass1_line_image = line_debug_image

		# So, ideally now we have 4 lines that fit the timing track. Now we need to go back and find actual blocks on the timing track
		# so we look for things that might be timing track blocks, and would rather find too many than too few, as opposed to the
		# previous search
		candidate_timing_blocks, blocks_debug_image_2 = find_candidate_blocks(thresh, image.shape, tight=False)
		timing_track_contours_image = np.zeros(image.shape, dtype = "uint8")
		for c in candidate_timing_blocks:
			cv2.drawContours(timing_track_contours_image, [c], -1, (0,255,255),-1)


		top = []
		bottom = []
		left = []
		right = []

		# probably from https://stackoverflow.com/questions/39840030/distance-between-point-and-a-line-from-two-points/39840218
		def dist_to_line(p1, p2, p3):
			d = np.linalg.norm(np.cross(p2-p1, p1-p3))/np.linalg.norm(p2-p1)
			return d

		np_top_start = np.array(top_start)
		np_top_stop = np.array(top_stop)
		np_bottom_start = np.array(bottom_start)
		np_bottom_stop = np.array(bottom_stop)
		np_left_start = np.array(left_start)
		np_left_stop = np.array(left_stop)
		np_right_start = np.array(right_start)
		np_right_stop = np.array(right_stop)

		append_thresh = 25 

		for c in candidate_timing_blocks:
			box_center = np.array(find_center(c))

			top_dist = dist_to_line(np_top_start, np_top_stop, box_center) 
			bottom_dist =  dist_to_line(np_bottom_start, np_bottom_stop, box_center) 
			left_dist =  dist_to_line(np_left_start, np_left_stop, box_center) 
			right_dist= dist_to_line(np_right_start, np_right_stop, box_center) 
	
			if top_dist < append_thresh:
				top.append(c)
			if bottom_dist < append_thresh:
				bottom.append(c)
			if left_dist < append_thresh:
				left.append(c)
			if right_dist < append_thresh:
				right.append(c)


		#new_image = cv2.addWeighted(line_debug_image 0.3, orig_img, 0.7, 0)
		#print("Final count: %d" % (len(top) + len(bottom)+len(left)+len(right)))

		#print("Drawing a line in findboxes helper")
		#cv2.line(new_image, (100,100), (400,400), (0,255,255),5)
		return top, bottom, left, right, blocks_debug_image_2, timing_track_contours_image


	def find_boxes(self):
		try:
			top, bottom, left, right, candidate_blocks_debug_image, timing_track_contours_image = self._find_boxes(self.image, debug=False, warped=False)
		except NoLinesException:
			self.express_vote = True
			self.detect_barcodes()	
			return
		except Exception as e:
			print("Some other exception straight away?: %s" % (e), flush=True)
			raise
		self.pass1_candidate_blocks_debug = candidate_blocks_debug_image
		self.pass1_timing_track_contours_image = timing_track_contours_image
		pass1_corners_image = self.image.copy()
		#cv2.drawContours(pass1_corners_image, top, -1, (0,128,255), -1) 
		cv2.drawContours(pass1_corners_image, left, -1, (128,128,255), -1) 
		cv2.drawContours(pass1_corners_image, right, -1, (0,128,255), -1) 
		#cv2.drawContours(pass1_corners_image, bottom, -1, (0,128,255), -1) 
		self.pass1_corners_image = pass1_corners_image
		top_left_box, top_right_box, bottom_left_box, bottom_right_box = find_corners(top, bottom, left, right)
		#print("TopL: %d BottomL: %d TopR %d BottomR %d" % (len(top_left), len(bottom_left), len(top_right), len(bottom_right)))


		new_image = self.image.copy()
		#pass1_corners_image = self.image.copy()
		#cv2.drawContours(pass1_corners_image, top, -1, (0,128,255), -1) 
		#cv2.drawContours(pass1_corners_image, [top_left_box], -1, (0,0,255), -1) 
		#cv2.drawContours(pass1_corners_image, [bottom_left_box], -1, (255,0,0), -1) 
		#cv2.drawContours(pass1_corners_image, [top_right_box], -1, (0,255,255), -1) 
		#cv2.drawContours(pass1_corners_image, [bottom_right_box], -1, (0,255,0), -1) 
		#cv2.drawContours(pass1_corners_image, right, -1, (0,255,0), -1) 
		#self.pass1_corners_image = pass1_corners_image

		#left = contours.sort_contours(left, "top-to-bottom")[0]
		#for i,c in enumerate(left):
			#print("Adding %d to the image" % (i))
			#(x, y, w, h) = cv2.boundingRect(c)
			#cv2.putText(new_image, "%d" % (i), (x+70, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
		#print("Found %d on left" % (len(left)))

		#
		#
		# dewarping / phase 2
		#
		#

		xformed_image = dewarp(new_image, top_left_box, top_right_box, bottom_left_box, bottom_right_box)
		self.image = xformed_image
		try:
			top, bottom, left, right, candidate_blocks_debug_image, timing_track_contours_image = self._find_boxes(xformed_image, debug=False, warped=True)
		except NoLinesException:
			return
		except Exception as e:
			#print("Pass 2 Some other exception?: %s" % (e), flush=True)
			raise 

		top_left_box, top_right_box, bottom_left_box, bottom_right_box = find_corners(top, bottom, left, right)
		pass2_corners_image = self.image.copy()
		cv2.drawContours(pass2_corners_image, top, -1, (0,128,255), -1) 
		cv2.drawContours(pass2_corners_image, [top_left_box], -1, (0,0,255), -1) 
		cv2.drawContours(pass2_corners_image, [bottom_left_box], -1, (255,0,0), -1) 
		cv2.drawContours(pass2_corners_image, [top_right_box], -1, (0,255,255), -1) 
		cv2.drawContours(pass2_corners_image, [bottom_right_box], -1, (0,255,0), -1) 
		self.pass2_corners_image = pass2_corners_image
		self.pass2_xformed_raw_image = xformed_image
		self.pass2_candidate_blocks = candidate_blocks_debug_image
		self.pass2_timing_track_contours_image = timing_track_contours_image


		top = contours.sort_contours(top, "left-to-right")[0]
		bottom = contours.sort_contours(bottom, "left-to-right")[0]
		left = contours.sort_contours(left, "top-to-bottom")[0]
		right = contours.sort_contours(right, "top-to-bottom")[0]

		style = []
		self.style_image = xformed_image.copy()
		for i,c in enumerate(left):
			#print("Adding %d to the image" % (i))
			(x, y, w, h) = cv2.boundingRect(c)
			area = cv2.contourArea(c)
			if area > 600:
				style.append(str(i))
				cv2.drawContours(xformed_image, [c], -1, (0,255,255), 2)
			(cx,cy) = find_center(c)
			cv2.putText(self.style_image, "%d" % (i), (cx+450, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
			cv2.line(self.style_image, (cx,cy), (cx+1600, cy),(0,255,0),3)
		if style:
			self.detected_style = ",".join(style)
		else:
			self.detected_style = "Unknown"
		if self.cvr:
			missing_counter = 2
			for contest in self.cvr.get_contests():
				for option in contest.get_contest_options():
					if option.valid:
						(cx, junk) = find_center(top[option.x])
						(junk, cy) = find_center(left[option.y])
						cv2.putText(self.style_image, "%s" % (option.contest_option), (cx+100, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
					else:
						cv2.putText(self.style_image, "FIXME: %s" % (option.contest_option), (1500, (missing_counter*50)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
						missing_counter = missing_counter + 1
					#print('%s: %d %d' % (option.contest_option, option.x, option.y))

		#self.styleLoad()
		#print("Found %d on left" % (len(left)))
		#cv2.putText(xformed_image, "%d" % (len(left) + len(right) + len(top) + len(bottom)), (1500, 2500), cv2.FONT_HERSHEY_SIMPLEX,3.0, (0, 0, 255), 4)
		#if(len(left) + len(right) + len(top) + len(bottom)) != 186:
		#	raise Exception("Incorrect number of boxes!: %d %d %d %d" % (len(left), len(right), len(top), len(bottom)))
			#print("Incorrect number of boxes!: %d %d %d %d" % (len(left), len(right), len(top), len(bottom)))
			#pass
		self.boxcount = len(left) + len(right) + len(top) + len(bottom)
		#self.image = thresh2

		(col1_x, junk) = find_center(top[1])
		(col2_x, junk) = find_center(top[9])
		(col3_x, junk) = find_center(top[17])

		left_ys = []
		for leftbox in left:
			(cx, cy) = find_center(leftbox) 
			left_ys.append(cy)

		col1_centers = [(col1_x, left_y) for left_y in left_ys]
		col2_centers = [(col2_x, left_y) for left_y in left_ys]
		col3_centers = [(col3_x, left_y) for left_y in left_ys]

		#for centers in col1_centers:
			#cv2.rectangle(xformed_image, (centers[0] - 15, centers[1]-15), (centers[0]+15, centers[1]+15), (0,0,255), 2)	
			#cv2.circle(xformed_image, centers, 5, (255,0,0), 2)	

		self.image = xformed_image
		self.top_rects = top
		self.bottom_rects = bottom	
		self.left_rects = left
		self.right_rects = right
		self.col1_centers = col1_centers
		self.col2_centers = col2_centers
		self.col3_centers = col3_centers
		return


	# FIXME - tracking 3 columns was a dumb idea, replace it to just use timing track centers directly
	def count_pixels(self, image, x_t, y_t):
		mask = np.zeros(image.shape, dtype="uint8")
		if x_t == 1:
			x_target = self.col1_centers[y_t][0]
			y_target = self.col1_centers[y_t][1]
		if x_t == 9:
			x_target = self.col2_centers[y_t][0]
			y_target = self.col2_centers[y_t][1]
		if x_t == 17:
			x_target = self.col3_centers[y_t][0]
			y_target = self.col3_centers[y_t][1]

		L = [[x_target-15, y_target-15], [x_target+15, y_target-15], [x_target+15, y_target+15], [x_target-15, y_target+15]]
		c = np.array(L).reshape((-1,1,2)).astype(np.int32)
		cv2.drawContours(mask, [c], -1, 255, -1)
		mask = cv2.bitwise_and(image, image, mask=mask)
		total = float(cv2.countNonZero(mask)) / (30.0 * 30.0)
		return total, x_target, y_target

	def detect_barcodes(self):
		tempimage = cv2.cvtColor(self.image.copy(), cv2.COLOR_BGR2GRAY)
		thresh = cv2.threshold(tempimage, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

		marks = {}
		for barcode in decode(self.image):
			decoded = barcode.data.decode("utf-8")
			if len(decoded) == 6:
				marks[decoded[0:4]] = True
			#	print(decoded)
			if len(decoded) > 6:
				self.detected_style = decoded
			
		self.barcodes = marks

	def decode_barcodes(self):
		marks = self.barcodes
		for contest in self.cvr.get_contests():
			for option in contest.get_contest_options():
				tempkey = "%02d%02d" % (option.x, option.y)
				if tempkey in marks:
					option.pixel_pcts = 1.0
				else:
					option.pixel_pcts = 0.0


	def check_marks(self, cvr):
		tempimage = cv2.cvtColor(self.image.copy(), cv2.COLOR_BGR2GRAY)
		thresh = cv2.threshold(tempimage, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

		for contest in self.cvr.get_contests():
			for option in contest.get_contest_options():
				pixel_pct, xcoord, ycoord = self.count_pixels(thresh, option.x, option.y)
				option.pixel_pcts = pixel_pct
				option.xpixel = xcoord
				option.ypixel = ycoord

				
	
	def score(self):		
		if self.express_vote:
			self.decode_barcodes()
		else:
			self.check_marks(self.cvr)
					
		for contest in self.cvr.get_contests():
			voted = "Unknown"
			count = 0
			for option in contest.get_contest_options():
				percent = option.pixel_pcts
				if option.pixel_pcts > 0.18:
					count += 1
					voted = option.contest_option	
			if count > 1:
				voted = "overvote"
			if count == 0:
				voted = "undervote"
			contest.contest_option_vote_scored = voted

		# todo, write a real helper for a serializer for this
		votes = []
		for contest in self.cvr.get_contests():
			pixel_pcts = {}
			for option in contest.get_contest_options():
				pixel_pcts[option.contest_option] = option.pixel_pcts
			votes.append({"race": contest.contest_name, "details": {"scored":contest.contest_option_vote_scored, "ESS": contest.contest_option_vote_ess}, "pixels":pixel_pcts})
	
		self.scored_image = self.image.copy()	

		if not self.express_vote:
			for contest in self.cvr.get_contests():
				for option in contest.get_contest_options():	
					x_target = option.xpixel
					y_target = option.ypixel
					L = [[x_target-15, y_target-15], [x_target+15, y_target-15], [x_target+15, y_target+15], [x_target-15, y_target+15]]
					c = np.array(L).reshape((-1,1,2)).astype(np.int32)
					#cv2.drawContours(self.scored_image, [c], -1, (255,0,0), 2)
					if contest.contest_option_vote_scored == option.contest_option:
						cv2.drawContours(self.scored_image, [c], -1, (255,0,0), 2)
						for i, line in enumerate(option.contest_option.split('/')):
							y_tmp = y_target + i*35
							cv2.putText(self.scored_image, line, (x_target+175, y_tmp), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,0,0), 2)	
					if contest.contest_option_vote_scored == "overvote":
						cv2.drawContours(self.scored_image, [c], -1, (0,0,255), 2)
						cv2.putText(self.scored_image, "Overvote", (x_target+175, y_target), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)	
				
		retval = {}
		retval["votes"] = votes
		retval["style"] = self.style
		retval["detectedStyle"] = self.detected_style
		retval["styleFile"] = "FIXME"
		retval["expressVote"] = self.express_vote
		if self.express_vote:
			retval["barcodes"] = self.barcodes
		return retval

