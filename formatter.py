"""

Version 1.0 ,  Takes raw data from json file and make it into a slightly more organized version, 
removing alot of useless bulk data that is  unneccesary or repeated 

The cleand up json file keeps track of things like which team won, player list and stats, death details.. etc 


right now i coded it to allow user to just select a json file, but again will change this later to be automated
so it can be used in main code easier



"""

import json
import os
import sys


# ---------------------------------------------------------------------
# these are just used to keep track of timers in game for important intervals
# 10 min is our lane indicator, we can use data at this timestamp to see if someone has a bad lane phase
#20 mins if your rough midgame phase, usually this can tell us if someone has a bad mid game
# 30 mins is late game, so we can see how users preform in late game 
# ---------------------------------------------------------------------
INTERVAL_TARGETS_S = {
    "10_min": 600,
    "20_min": 1200,
    "30_min": 1800,
}

#function is used to return the nearest snapshot we hae closest to the X minute mark, 
# our params stats list and target_s , just represent the stats closest to target time 
def nearest_snapshot(stats_list, target_s):
    
    if not stats_list:
        return None
    best = min(stats_list, key=lambda s: abs(s.get("time_stamp_s", 0) - target_s))
    return best

# pulls raw fields out of the stats, snap is the current snapshot, custom stats name lookup is used to check
#weird json values they have, 2 tables they have in the json called custom stats, one in the user which gives a
# type which is just some random integer and a value
# and there is a table which essentially assigns each of these values a name, 
# so to simplify i just combined the tables and passed through the lookup it changes at each snapshot and per player
def snapshot_to_entry(snap, custom_stats_name_lookup):
    """Pull the raw fields out of one stats snapshot. No KDA math done here --
    kills/deaths/assists are included as raw numbers only, left for you to
    compute whatever ratios/stats you want yourself.

    custom_user_stats lives INSIDE each snapshot (it's per-player,
    per-moment-in-time, not just once per player) -- so it gets joined
    against the name lookup table right here."""
    return {
        "actual_snapshot_time_s": snap.get("time_stamp_s"),
        "kills": snap.get("kills"),
        "deaths": snap.get("deaths"),
        "assists": snap.get("assists"),
        "net_worth": snap.get("net_worth"),
        "creep_kills": snap.get("creep_kills"),
        "neutral_kills": snap.get("neutral_kills"),
        "possible_creeps": snap.get("possible_creeps"),
        "creep_damage": snap.get("creep_damage"),
        "player_damage": snap.get("player_damage"),
        "neutral_damage": snap.get("neutral_damage"),
        "boss_damage": snap.get("boss_damage"),
        "denies": snap.get("denies"),
        "player_healing": snap.get("player_healing"),
        "ability_points": snap.get("ability_points"),
        "self_healing": snap.get("self_healing"),
        "player_damage_taken": snap.get("player_damage_taken"),
        "weapon_power": snap.get("weapon_power"),
        "tech_power": snap.get("tech_power"),
        "shots_hit": snap.get("shots_hit"),
        "shots_missed": snap.get("shots_missed"),
        "damage_absorbed": snap.get("damage_absorbed"),
        "absorption_provided": snap.get("absorption_provided"),
        "hero_bullets_hit": snap.get("hero_bullets_hit"),
        "hero_bullets_hit_crit": snap.get("hero_bullets_hit_crit"),
        "heal_prevented": snap.get("heal_prevented"),
        "heal_lost": snap.get("heal_lost"),
        "gold_sources": snap.get("gold_sources"),  # again same issue with custom stats but no proper matching
        "custom_user_stats": build_custom_stats(snap.get("custom_user_stats"), custom_stats_name_lookup),
    }

# builds the snapshots of the closest intervals, 10/20/30/end of game 
#had to make sure to include a t
def build_interval_report(stats_list, duration_s, custom_stats_name_lookup):
    report = {}

    for label, target_s in INTERVAL_TARGETS_S.items():
        if duration_s is not None and duration_s < target_s:
            # Match ended before this interval would have happened
            report[label] = None
            continue

        snap = nearest_snapshot(stats_list, target_s)
        if snap is None:
            report[label] = None
            continue

        report[label] = snapshot_to_entry(snap, custom_stats_name_lookup)

    # Whatever the last snapshot in the match happened to be (usually end of game)
    if stats_list:
        report["last_available"] = snapshot_to_entry(stats_list[-1], custom_stats_name_lookup)
    else:
        report["last_available"] = None

    return report

#this joins together the players custom stats and the players name and id 
def build_custom_stats(player_custom_stats, name_lookup):
    """Player-level custom_user_stats only gives {id, value} pairs. The
    match-level custom_user_stats list is the lookup table that maps each
    id to a human-readable name ({id, name}). This joins the two together
    so each entry has id, name, AND value in one place.

    If the player has no custom stats recorded (commonly null), this just
    returns None -- nothing to join.
    """
    if not player_custom_stats:
        return None

    joined = []
    for entry in player_custom_stats:
        stat_id = entry.get("id")
        joined.append({
            "id": stat_id,
            "name": name_lookup.get(stat_id),  # None if id isn't in the lookup table
            "value": entry.get("value")
        })
    return joined

#used to remove a bunch of unneccesary lines of code from the paths field, such as %hp throughout the game, combat type,
#move types,... etc just not needed and takes up space, only kept the players x,y, positions and their max and min x,y
def strip_path_fields(match_paths):
    """match_paths.paths has health / combat_type / move_type per player,
    which we don't want kept. Returns a copy of match_paths with just
    player_slot, the bounding box (x_min/y_min/x_max/y_max), and the raw
    x_pos / y_pos position arrays."""
    if not match_paths:
        return match_paths

    stripped_paths = []
    for path_entry in match_paths.get("paths", []):
        stripped_paths.append({
            "player_slot": path_entry.get("player_slot"),
            "x_min": path_entry.get("x_min"),
            "y_min": path_entry.get("y_min"),
            "x_max": path_entry.get("x_max"),
            "y_max": path_entry.get("y_max"),
            "x_pos": path_entry.get("x_pos"),
            "y_pos": path_entry.get("y_pos"),
        })

    return {
        "version": match_paths.get("version"),
        "interval_s": match_paths.get("interval_s"),
        "x_resolution": match_paths.get("x_resolution"),
        "y_resolution": match_paths.get("y_resolution"),
        "paths": stripped_paths,
    }

#builds the entire report of the player, with all their assigned information and data 
def build_player_report(player, duration_s, custom_stats_name_lookup):
    return {
        "account_id": player.get("account_id"),
        "player_slot": player.get("player_slot"),
        "team": player.get("team"),
        "hero_id": player.get("hero_id"),
        "level": player.get("level"),
        "assigned_lane": player.get("assigned_lane"),

        
        "final_totals": {
            "kills": player.get("kills"),
            "deaths": player.get("deaths"),
            "assists": player.get("assists"),
            "net_worth": player.get("net_worth"),
            "last_hits": player.get("last_hits"),
            "denies": player.get("denies"),
            "ability_points": player.get("ability_points"),
        },

        # Every death this player had, full detail (position, killer, timing)
        "death_details": player.get("death_details", []),

        # Stats at 10/20/30 min + last available snapshot. -
       
        "stats_at_intervals": build_interval_report(player.get("stats", []), duration_s, custom_stats_name_lookup),

        #all stats just incase i need them 
        "all_stats_snapshots": player.get("stats", []),

        #these are important lowkey 
        "items": player.get("items"),
        "power_up_buffs": player.get("power_up_buffs"),
        "accolades": player.get("accolades"),
        "mvp_rank": player.get("mvp_rank"),
        "player_match_outcome": player.get("player_match_outcome"),
        "player_rank_data": player.get("player_rank_data"),
        "abandon_match_time_s": player.get("abandon_match_time_s"),

        

        # Unmapped / unknown-meaning fields  (idk what any of this does so left just in case)
        "UNMAPPED_stats_type_stat": player.get("stats_type_stat"), #no clue
        "UNMAPPED_ability_stats": player.get("ability_stats"), 
        "UNMAPPED_player_tracked_stats": player.get("player_tracked_stats"),
        "UNMAPPED_hero_data": player.get("hero_data"),  
    }


def extract_match(data):

    # -----------------------------------------------------------------
    # TODO : Right now this program cant tell whether the match entered is a real match
    # i think this is an easy fix whenever i properly implement user functionality
    #since the user wont ever input a game, and there will be an error initially if the game doesnt exist
    #or cant be retreived so i didnt bother 
    #
    # probably more stuff to add here later on but fine for now 
    # -----------------------------------------------------------------

    info = data["match_info"]
    duration_s = info.get("duration_s")

    # Build the id
    custom_stats_name_lookup = {}
    for entry in (info.get("custom_user_stats") or []):
        custom_stats_name_lookup[entry.get("id")] = entry.get("name")

    report = {
        "match_id": info.get("match_id"),
        "duration_s": duration_s,
        "match_outcome": info.get("match_outcome"),
        "winning_team": info.get("winning_team"),
        "start_time": info.get("start_time"),

        "game_mode": info.get("game_mode"),
        "match_mode": info.get("match_mode"),
        "ranked_type": info.get("ranked_type"),
        "rank_interval": info.get("rank_interval"),

        "average_badge_team0": info.get("average_badge_team0"),
        "average_badge_team1": info.get("average_badge_team1"),

        "objectives": info.get("objectives"),
        "mid_boss": info.get("mid_boss"),

        "hero_build_ids": data.get("hero_build_ids"),
        "banned_hero_ids": data.get("banned_hero_ids"),

        "players": [build_player_report(p, duration_s, custom_stats_name_lookup) for p in info.get("players", [])],

        # id -> name lookup table itself, kept here too in case you want to
        # look up a stat name directly without digging into a player
        "custom_user_stats_lookup": info.get("custom_user_stats"),

        # Unmapped / unknown-meaning match-level fields (useless stuff kept or maybe important things)
        "UNMAPPED_objectives_mask_team0": info.get("objectives_mask_team0"),
        "UNMAPPED_objectives_mask_team1": info.get("objectives_mask_team1"),
        "UNMAPPED_legacy_objectives_mask": info.get("legacy_objectives_mask"),
        "UNMAPPED_match_tracked_stats": info.get("match_tracked_stats"),
        "UNMAPPED_team_score": info.get("team_score"),
        "UNMAPPED_teams": info.get("teams"),
        "UNMAPPED_match_paths": strip_path_fields(info.get("match_paths")),   # health/combat_type/move_type stripped out
        "UNMAPPED_damage_matrix": info.get("damage_matrix"),
        "UNMAPPED_watched_death_replays": info.get("watched_death_replays"),
        "UNMAPPED_match_pauses": info.get("match_pauses"),
        "UNMAPPED_not_scored": info.get("not_scored"),
    }

    return report

#process the file 
def process_file(input_path, output_path):
    try:
        f = open(input_path)
        data = json.load(f)
        f.close()

        report = extract_match(data)

        f = open(output_path, "w")
        json.dump(report, f, indent=2)
        f.close()

        print("Extracted:", input_path, "->", output_path)

    except Exception as e: # i check here to see if file works, but i want to check the error before here,
        #this might throw too late, better safe than sorry
    
        print("FAILED on file:", input_path)
        print("  Reason:", e)


#used ai here since this isnt going to be apart of the final project, and
#didnt want to waste time making a simple file picker that wont be used after its fully updated 

def pick_file_manually():
    
    try:
        import tkinter
        from tkinter import filedialog
    except Exception as e:
        print("File picker isn't available here:", e)
        print("Usage: python extract_match.py path/to/match.json [output.json]")
        return None

    root = tkinter.Tk()
    root.withdraw()
    chosen = filedialog.askopenfilename(
        title="Select a Deadlock match JSON file",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    root.destroy()

    if not chosen:
        print("No file selected.")
        return None

    return chosen

#same thing here
def main():
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
    else:
        # No path given on the command line -- let you pick manually.
        input_path = pick_file_manually()
        if not input_path:
            return

    if os.path.isdir(input_path):
        output_folder = os.path.join(input_path, "extracted")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        for filename in os.listdir(input_path):
            if filename.lower().endswith(".json"):
                full_input = os.path.join(input_path, filename)
                output_name = "extracted_" + filename
                full_output = os.path.join(output_folder, output_name)
                process_file(full_input, full_output)

    else:
        if len(sys.argv) >= 3:
            output_path = sys.argv[2]
        else:
            base = os.path.splitext(input_path)[0]
            output_path = base + "_extracted.json"

        process_file(input_path, output_path)


if __name__ == "__main__":
    main()