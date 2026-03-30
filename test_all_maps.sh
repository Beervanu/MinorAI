for f in ./maps/*; do
    map_s="$f"
    replay_s="./Replays/$(basename "$f")"
    replay_s="${replay_s/map26/replay26}"
    cambc run closedAI closedAI "$map_s" --replay "$replay_s"
done