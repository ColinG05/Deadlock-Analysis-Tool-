"""
Deadlock Match Data Extractor
------------------------------
Takes a raw match metadata JSON (from api.deadlock-api.com) and pulls out
a clean, organized report:
  - match outcome / winner
  - full player list (account_id, slot, hero_id, etc.)
  - full death_details per player
  - stat snapshots at 10 / 20 / 30 min (closest available snapshot to each),
    plus a final "last_available" snapshot which is just whatever the last
    entry in the game's stats history was (usually end of game)
  - objectives, mid_boss events, power_up_buffs, accolades, rank data
  - anything currently unmapped is kept AS-IS in the output (prefixed
    UNMAPPED_) so no data is lost, even though we don't know what every
    field means yet

This program is intentionally separate from whatever script you use to
pull matches from the API. This one only ever works on a JSON file you
already have on disk -- either point it at a file/folder from the command
line, or just run it with no arguments and a file picker window will pop
up so you can choose the match JSON manually.

No f-strings are used anywhere in this file (keeps old VS Python parsers happy).

USAGE:
    python extract_match.py                          (opens a file picker)
    python extract_match.py path/to/match_12345.json
    python extract_match.py path/to/match_12345.json my_output.json
    python extract_match.py path/to/folder_of_matches/          (batch mode)

If you point it at a folder, it will process every .json file inside and
write one report per match into an "extracted" subfolder next to it.
"""

import json
import os
import sys


# ---------------------------------------------------------------------
# Which points in the match you want stat snapshots for, in seconds.
# We always grab the CLOSEST available snapshot to each target and tell
# you exactly which timestamp was actually used.
# ---------------------------------------------------------------------
INTERVAL_TARGETS_S = {
    "10_min": 600,
    "20_min": 1200,
    "30_min": 1800,
}


def nearest_snapshot(stats_list, target_s):
    """Return the stats snapshot whose time_stamp_s is closest to target_s."""
    if not stats_list:
        return None
    best = min(stats_list, key=lambda s: abs(s.get("time_stamp_s", 0) - target_s))
    return best


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
        "gold_sources": snap.get("gold_sources"),  # source IDs kept raw, unmapped
        "custom_user_stats": build_custom_stats(snap.get("custom_user_stats"), custom_stats_name_lookup),
    }


def build_interval_report(stats_list, duration_s, custom_stats_name_lookup):
    """Build the 10/20/30-min snapshots (closest available), plus a
    'last_available' snapshot which is just whatever the final entry in
    the stats history was.

    EDGE CASE: if the match didn't last long enough to ever reach a given
    target (e.g. a 12-minute match has no real '30 min' point), that
    interval is set to None instead of misleadingly grabbing an early
    snapshot and mislabeling it. The program keeps running either way --
    it never crashes or stops just because a short match is missing some
    of the later intervals.
    """
    report = {}

    for label, target_s in INTERVAL_TARGETS_S.items():
        if duration_s is not None and duration_s < target_s:
            # Match ended before this interval would have happened.
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


def build_player_report(player, duration_s, custom_stats_name_lookup):
    return {
        "account_id": player.get("account_id"),
        "player_slot": player.get("player_slot"),
        "team": player.get("team"),
        "hero_id": player.get("hero_id"),
        "level": player.get("level"),
        "assigned_lane": player.get("assigned_lane"),

        # Final totals (convenience -- same numbers as the last stats snapshot,
        # but these are the "official" top-level fields the API gives per player)
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

        # Stats at 10/20/30 min + last available snapshot. No KDA computed --
        # raw kills/deaths/assists numbers are in each snapshot for you to
        # do that math yourself. Each snapshot's custom_user_stats is also
        # joined with names here.
        "stats_at_intervals": build_interval_report(player.get("stats", []), duration_s, custom_stats_name_lookup),

        # Full raw stat snapshot history too, in case you want more than
        # just the chosen intervals later
        "all_stats_snapshots": player.get("stats", []),

        "items": player.get("items"),
        "power_up_buffs": player.get("power_up_buffs"),
        "accolades": player.get("accolades"),
        "mvp_rank": player.get("mvp_rank"),
        "player_match_outcome": player.get("player_match_outcome"),
        "player_rank_data": player.get("player_rank_data"),
        "abandon_match_time_s": player.get("abandon_match_time_s"),

        # id + name + value joined together, per snapshot (see build_custom_stats
        # and snapshot_to_entry above -- custom_user_stats lives inside each
        # time snapshot, not once per player)

        # Unmapped / unknown-meaning fields -- kept as-is so nothing is lost
        "UNMAPPED_stats_type_stat": player.get("stats_type_stat"),
        "UNMAPPED_ability_stats": player.get("ability_stats"),
        "UNMAPPED_player_tracked_stats": player.get("player_tracked_stats"),
        "UNMAPPED_hero_data": player.get("hero_data"),
    }


def extract_match(data):

    # -----------------------------------------------------------------
    # TODO (your area): REAL MATCH CHECK
    #
    # This program assumes the JSON handed to it is always a real,
    # already-fetched match (not a rate-limit error, not an empty
    # response, etc.). Add your own validation here if you want it --
    # for example, checking that "match_info" exists in `data`,
    # checking duration_s is nonzero, checking for unexpected fields
    # that only show up in error responses, etc.
    #
    # Decide yourself what should happen if the check fails (skip the
    # file, raise an error, log it somewhere, etc.) -- left blank
    # intentionally so you can wire this up however you want.
    # -----------------------------------------------------------------

    info = data["match_info"]
    duration_s = info.get("duration_s")

    # Build the id -> name lookup table from match_info.custom_user_stats,
    # so each player's custom_user_stats (id + value only) can be joined
    # with the name.
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

        # Unmapped / unknown-meaning match-level fields -- kept as-is
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

    except Exception as e:
        # Something went wrong with this specific file -- print the error
        # and keep going rather than crashing the whole batch run.
        print("FAILED on file:", input_path)
        print("  Reason:", e)


def pick_file_manually():
    """Opens a simple file picker window so you can choose a match JSON
    without typing a path. Falls back to printing usage info if a display
    isn't available (e.g. running somewhere without a GUI)."""
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