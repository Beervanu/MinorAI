Get-ChildItem -Path "./maps" -Name |
ForEach-Object {
	$map_s = "./maps/"+ $_
	$replay_s = "./Replays/"+ $_
	$replay_s = $replay_s -replace "map26", "replay26"
	cambc run closedAI closedAI $map_s --replay $replay_s
}