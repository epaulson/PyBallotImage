import glob
import os
import sys
from tqdm import tqdm
from collections import defaultdict
styles = {}
examples = defaultdict(list)
import json


if len(sys.argv) < 3:
    print("Need to specify a subdir: process.py <src subdir> <target output>")
    exit(0)


files = glob.glob(sys.argv[1] + '/*i.pdf')
#for file in tqdm(files[:100]):
#for file in files[:100]:
for file in tqdm(files):
    f = os.path.basename(file)
    name = os.path.splitext(f)[0]
    #print(name)
    (junk, actual) = name.split('\\')
    name = actual
    stylelist = "%s" % ('default')
    styles[stylelist] = styles.get(stylelist, 0) + 1
    examples['default'].append(os.path.splitext(name)[0])
    subdir = os.path.basename(os.path.dirname(file))
    targetdir = sys.argv[2] + "/" + subdir
    if not os.path.exists(targetdir):
        os.mkdir(targetdir) 
    #print("pdfimages -tiff \'%s\' \'%s/%s\'" % (file, targetdir, name))
    os.system("pdfimages -png \'%s\' \'%s/%s\'" % (file, targetdir, name))
	
#for key in styles:
#    print("Style: %d" % styles[key])
#    print(examples[key][:10])
#    print('\n\n')
#exit(0)

ballots = []
for key in styles:
    d = {}
    d["text"]= key + "(%d)" % (len(examples[key]))
    d["selectable"] = False
    d["state"] = {"expanded": False}
    d["nodes"] = [{"text": x} for x in examples[key]]
    ballots.append(d)

#print(json.dumps(ballots))

#print(ballots)
#with open('data.txt', 'w') as outfile:
#    json.dump(ballots, outfile)
