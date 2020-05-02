{% extends "base.html" %}
{% block content %}
<?
$dnm = dirname(__FILE__);
require_once $dnm.'/config.php'
require_once $dnm.'/db.php';

date_default_timezone_set('Europe/Rome');
$GLOBALS['db'] = new DBPDO();

define('DATABASE_HOST', 'localhost');
define('DATABASE_USER', 'Debian');
define('DATABASE_PASS', 'moem0e');
define('DATABASE_NAME', 'Ainu');
define('DATABASE_WHAT', 'host');


		foreach ($rankRequests as $req) {
			$criteria = $req["type"] == "s" ? "beatmapset_id" : "beatmap_id";
			$b = $GLOBALS["db"]->mysql_fetch("SELECT beatmapset_id, song_name, ranked FROM beatmaps WHERE ".$criteria." = ? LIMIT 1", [$req["bid"]]);

			if ($b) {
				$matches = [];
				if (preg_match("/(.+)(\[.+\])/i", $b["song_name"], $matches)) {
					$song = $matches[1];
				} else {
					$song = "Wat";
				}
			} else {
				$song = "Unknown";
			}

			if ($req["type"] == "s")
				$bsid = $req["bid"];
			else
				$bsid = $b ? $b["beatmapset_id"] : 0;

			$today = !($req["time"] < time()-86400);
			$beatmaps = $GLOBALS["db"]->fetchAll("SELECT song_name, beatmap_id, ranked, difficulty_std, difficulty_taiko, difficulty_ctb, difficulty_mania FROM beatmaps WHERE beatmapset_id = ? LIMIT 15", [$bsid]);
			$diffs = "";
			$allUnranked = true;
			$forceParam = "1";
			$modes = [];
			foreach ($beatmaps as $beatmap) {
				$icon = ($beatmap["ranked"] >= 2) ? "check" : "times";
				$name = htmlspecialchars("$beatmap[song_name] ($beatmap[beatmap_id])");
				$diffs .= "<a href='#' data-toggle='popover' data-placement='bottom' data-content=\"$name\" data-trigger='hover'>";
				$diffs .= "<i class='fa fa-$icon'></i>";
				$diffs .= "</a>";
				if ($beatmap["difficulty_std"] > 0 && !in_array("std", $modes)) {
					$modes[] = "std";
				} else if ($beatmap["difficulty_std"] == 0) {
					if ($beatmap["difficulty_taiko"] > 0 && !in_array("taiko", $modes)) {
						$modes[] = "taiko";
					} else if ($beatmap["difficulty_ctb"] > 0 && !in_array("ctb", $modes)) {
						$modes[] = "ctb";
					} else if ($beatmap["difficulty_mania"] > 0 && !in_array("mania", $modes)) {
						$modes[] = "mania";
					}
				}

				if ($beatmap["ranked"] >= 2) {
					$allUnranked = false;
					$forceParam = "0";
				}
			}

			$modes = implode(", ", $modes);

			if (count($beatmaps) >= 15) {
				$diffs .= "...";
				$modes .= "...";
			}

			if ($req["blacklisted"] == 1) {
				$rowClass = "danger";
			} else if ($allUnranked) {
				$rowClass = $today ? "success" : "default";
			} else {
				$rowClass = "default";
			}

			echo "<tr class='$rowClass'>
				<td><a href='https://osu.ppy.sh/s/$bsid' target='_blank'>$req[type]/$req[bid]</a></td>
				<td>$song</td>
				<td>
					$diffs
				</td>
				<td>$modes</td>
				<td>$req[username]</td>
				<td>".timeDifference(time(), $req["time"])."</td>
				<td>
					<p class='text-center'>
						<a title='Edit ranked status' class='btn btn-xs btn-primary' href='rank/$bsid'><span class='glyphicon glyphicon-pencil'></span></a>
						<a title='Toggle blacklist' class='btn btn-xs btn-danger' href='submit.php?action=blacklistRankRequest&id=$req[id]&csrf=".csrfToken()."'><span class='glyphicon glyphicon-flag'></span></a>
					</p>
				</td>
			</tr>";
		}
		echo '</tbody>';
		echo '</table>';
		echo '</div>';

{% endblock %}
