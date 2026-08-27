# version 1.01, added proper comments just to make clearer , removed testing features
# 
#  looking at the code now testing purposes easier to save file
# probably will go back later on to change it to just create a json object that another program can call
# order on program would be like given matchid -> json object -> another json object, but that is a later issue 

import requests, json, os

match_id = 100547412
cache_file = "match_{}.json".format(match_id)


#file is already made so we can just forget about it 
if os.path.exists(cache_file):
    f = open(cache_file)
    data = json.load(f)
    f.close()
else: #match hasnt been tracked yet 
    resp = requests.get("https://api.deadlock-api.com/v1/matches/{}/metadata".format(match_id))
    data = resp.json()
    if "match_info" in data:
        f = open(cache_file, "w")
        json.dump(data, f, indent=2)
        f.close()

if "match_info" not in data: # for whatever reason it breaks 
    print("Something went wrong, got this instead:") # i should probably throw some error here instead, but again not too worried rn 
    print(data)
import requests, json, os

match_id = 100547412
cache_file = "match_{}.json".format(match_id)

if os.path.exists(cache_file):
    f = open(cache_file)
    data = json.load(f)
    f.close()
else:
    resp = requests.get("https://api.deadlock-api.com/v1/matches/{}/metadata".format(match_id))
    data = resp.json()
    if "match_info" in data:
        f = open(cache_file, "w")
        json.dump(data, f, indent=2)
        f.close()

if "match_info" not in data:
    print("Something went wrong, got this instead:")
    print(data)
else:
    print("Saved to", cache_file)
    print("Top-level keys:", list(data.keys()))
    print("match_info keys:", list(data["match_info"].keys()))
    if data["match_info"]["players"]:
        print("First player's keys:", list(data["match_info"]["players"][0].keys()))
