# This file is responsible for all the functionality
from urllib.request import urlopen

from config import UserConfig
import mysql.connector
from colorama import init, Fore
import redis
import bcrypt
import datetime
import requests
from discord_webhook import DiscordWebhook, DiscordEmbed
import time
import hashlib
import json
import pycountry
from osrparse import *
import os
from changelogs import Changelogs
import timeago

init()  # initialises colourama for colours
Changelogs.reverse()

print(fr"""{Fore.BLUE}  _____            _ _     _   _ _    _____                 _ _ 
 |  __ \          | (_)   | | (_) |  |  __ \               | | |
 | |__) |___  __ _| |_ ___| |_ _| | _| |__) |_ _ _ __   ___| | |
 |  _  // _ \/ _` | | / __| __| | |/ /  ___/ _` | '_ \ / _ \ | |
 | | \ \  __/ (_| | | \__ \ |_| |   <| |  | (_| | | | |  __/ |_|
 |_|  \_\___|\__,_|_|_|___/\__|_|_|\_\_|   \__,_|_| |_|\___|_(_)
 ---------------------------------------------------------------
{Fore.RESET}""")


# gotta def this here sorry
def ConsoleLog(Info: str, Additional: str = "", Type: int = 1):
    """Adds a log to the log file."""
    ### Types
    # 1 = Info
    # 2 = Warning
    # 3 = Error
    LogToAdd = {
        "Type": Type,
        "Info": Info,
        "Extra": Additional,
        "Timestamp": round(time.time())
    }
    if not os.path.exists("realistikpanel.log"):
        # if doesnt exist
        with open("realistikpanel.log", 'w') as json_file:
            json.dump([], json_file, indent=4)

    # gets current log
    with open("realistikpanel.log", "r") as Log:
        Log = json.load(Log)

    Log.append(LogToAdd)  # adds current log

    with open("realistikpanel.log", 'w') as json_file:
        json.dump(Log, json_file, indent=4)


try:
    mydb = mysql.connector.connect(
        host=UserConfig["SQLHost"],
        user=UserConfig["SQLUser"],
        passwd=UserConfig["SQLPassword"]
    )  # connects to database
    print(f"{Fore.GREEN} Successfully connected to MySQL!")
except Exception as e:
    print(f"{Fore.RED} Failed connecting to MySQL! Abandoning!\n Error: {e}{Fore.RESET}")
    ConsoleLog("Failed to connect to MySQL", f"{e}", 3)
    exit()

try:
    r = redis.Redis(host=UserConfig["RedisHost"], password=UserConfig["RedisPassword"], port=UserConfig["RedisPort"],
                    db=UserConfig["RedisDb"])  # establishes redis connection
    print(f"{Fore.GREEN} Successfully connected to Redis!")
except Exception as e:
    print(f"{Fore.RED} Failed connecting to Redis! Abandoning!\n Error: {e}{Fore.RESET}")
    ConsoleLog("Failed to connect to Redis", f"{e}", 3)
    exit()

mycursor = mydb.cursor()  # creates a thing to allow us to run mysql commands
mycursor.execute(f"USE {UserConfig['SQLDatabase']}")  # Sets the db to ripple
mycursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")

# public variables
PlayerCount = []  # list of players
CachedStore = {}


def DashData():
    # note to self: add data caching so data isnt grabbed every time the dash is accessed
    """Grabs all the values for the dashboard."""
    mycursor.execute("SELECT value_string FROM system_settings WHERE name = 'website_global_alert'")
    Alert = mycursor.fetchall()
    if len(Alert) == 0:
        # some ps only have home alert
        mycursor.execute("SELECT value_string FROM system_settings WHERE name = 'website_home_alert'")
        # if also that doesnt exist
        Alert = mycursor.fetchall()
        if len(Alert) == 0:
            Alert = [[]]
    Alert = Alert[0][0]
    if Alert == "":  # checks if no alert
        Alert = False

    totalPP = r.get("ripple:total_pp")  # Not calculated by every server .decode("utf-8")
    RegisteredUsers = r.get("ripple:registered_users")
    OnlineUsers = r.get("ripple:online_users")
    TotalPlays = r.get("ripple:total_plays")
    TotalScores = r.get("ripple:total_submitted_scores")

    # If we dont have variable(variable is None) will set it and get it again
    if not totalPP:
        r.set('ripple:total_pp', 0)
        totalPP = r.get("ripple:total_pp")
    if not RegisteredUsers:
        r.set('ripple:registered_users', 1)
        RegisteredUsers = r.get("ripple:registered_users")
    if not OnlineUsers:
        r.set('ripple:online_users', 1)
        OnlineUsers = r.get("ripple:online_users")
    if not TotalPlays:
        r.set('ripple:total_plays', 1)
        TotalPlays = r.get("ripple:total_plays")
    if not TotalScores:
        r.set('ripple:total_submitted_scores', 1)
        TotalScores = r.get("ripple:total_submitted_scores")
    response = {
        "RegisteredUsers": RegisteredUsers.decode("utf-8"),
        "OnlineUsers": OnlineUsers.decode("utf-8"),
        "TotalPP": f'{int(totalPP.decode("utf-8")):,}',
        "TotalPlays": f'{int(TotalPlays.decode("utf-8")):,}',
        "TotalScores": f'{int(TotalScores.decode("utf-8")):,}',
        "Alert": Alert
    }
    return response


def LoginHandler(username, password):
    """Checks the passwords and handles the sessions."""
    mycursor.execute(
        "SELECT username, password_md5, ban_datetime, privileges, id FROM users WHERE LOWER(username) = %s",
        (username.lower(),))
    User = mycursor.fetchall()
    if len(User) == 0:
        # when user not found
        return [False, "User not found. Maybe a typo?"]
    else:
        User = User[0]
        # Stores grabbed data in variables for easier access
        Username = User[0]
        PassHash = User[1]
        IsBanned = User[2]
        Privilege = User[3]
        id = User = User[4]

        # Converts IsBanned to bool
        if IsBanned == "0" or not IsBanned:
            IsBanned = False
        else:
            IsBanned = True

        # shouldve been done during conversion but eh
        if IsBanned:
            return [False, "You are banned... Awkward..."]
        else:
            if HasPrivilege(id):
                if checkpw(PassHash, password):
                    return [True, "You have been logged in!", {  # creating session
                        "LoggedIn": True,
                        "AccountId": id,
                        "AccountName": Username,
                        "Privilege": Privilege,
                        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2)  # so the token expires
                    }]
                else:
                    return [False, "Incorrect password"]
            else:
                return [False, "Missing privileges!"]


def TimestampConverter(timestamp, NoDate=1):
    """Converts timestamps into readable time."""
    date = datetime.datetime.fromtimestamp(int(timestamp))  # converting into datetime object
    # so we avoid things like 21:6
    # hour = str(date.hour)
    # minute = str(date.minute)
    # if len(hour) == 1:
    # hour = "0" + hour
    # if len(minute) == 1:
    # minute = "0" + minute
    if NoDate == 1:
        # return f"{hour}:{minute}"
        return date.strftime("%H:%M")
    if NoDate == 2:
        return date.strftime("%H:%M %d/%m/%Y")


def RecentPlays():
    """Returns recent plays."""
    # this is probably really bad
    mycursor.execute(
        "SELECT scores.beatmap_md5, users.username, scores.userid, scores.time, scores.score, scores.pp, scores.play_mode, scores.mods FROM scores LEFT JOIN users ON users.id = scores.userid WHERE users.privileges & 1 ORDER BY scores.time DESC LIMIT 10")
    plays = mycursor.fetchall()
    if UserConfig["HasRelax"]:
        # adding relax plays
        mycursor.execute(
            "SELECT scores_relax.beatmap_md5, users.username, scores_relax.userid, scores_relax.time, scores_relax.score, scores_relax.pp, scores_relax.play_mode, scores_relax.mods FROM scores_relax LEFT JOIN users ON users.id = scores_relax.userid WHERE users.privileges & 1 ORDER BY scores_relax.time DESC LIMIT 10")
        playx_rx = mycursor.fetchall()
        for plays_rx in playx_rx:
            # addint them to the list
            plays_rx = list(plays_rx)
            plays.append(plays_rx)
    PlaysArray = []
    # converting into lists as theyre cooler (and easier to work with)
    for x in plays:
        PlaysArray.append(list(x))

    # converting the data into something readable
    ReadableArray = []
    for x in PlaysArray:
        # yes im doing this
        # lets get the song name
        BeatmapMD5 = x[0]
        mycursor.execute("SELECT song_name FROM beatmaps WHERE beatmap_md5 = %s", (BeatmapMD5,))
        SongFetch = mycursor.fetchall()
        if len(SongFetch) == 0:
            # checking if none found
            SongName = "Invalid..."
        else:
            SongName = list(SongFetch[0])[0]
        # make and populate a readable dict
        Dicti = {}
        Mods = ModToText(x[7])
        if Mods == "":
            Dicti["SongName"] = SongName
        else:
            Dicti["SongName"] = SongName + " +" + Mods
        Dicti["Player"] = x[1]
        Dicti["PlayerId"] = x[2]
        Dicti["Score"] = f'{x[4]:,}'
        Dicti["pp"] = round(x[5])
        Dicti["Time"] = TimestampConverter(x[3])
        ReadableArray.append(Dicti)

    ReadableArray = sorted(ReadableArray, key=lambda k: k["Time"])  # sorting by time
    ReadableArray.reverse()
    return ReadableArray


def FetchBSData():
    """Fetches Bancho Settings."""
    mycursor.execute(
        "SELECT name, value_string, value_int FROM bancho_settings WHERE name = 'bancho_maintenance' OR name = 'menu_icon' OR name = 'login_notification'")
    Query = list(mycursor.fetchall())
    # bancho maintenence
    if Query[0][2] == 0:
        BanchoMan = False
    else:
        BanchoMan = True
    return {
        "BanchoMan": BanchoMan,
        "MenuIcon": Query[1][1],
        "LoginNotif": Query[2][1]
    }


def BSPostHandler(post, session):
    BanchoMan = post[0]
    MenuIcon = post[1]
    LoginNotif = post[2]

    # setting blanks to bools
    if BanchoMan == "On":
        BanchoMan = True
    else:
        BanchoMan = False
    if MenuIcon == "":
        MenuIcon = False
    if LoginNotif == "":
        LoginNotif = False

    # SQL Queries
    if MenuIcon != False:  # this might be doable with just if not BanchoMan
        mycursor.execute("UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'menu_icon'",
                         (MenuIcon,))
    else:
        mycursor.execute("UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'menu_icon'")

    if LoginNotif != False:
        mycursor.execute(
            "UPDATE bancho_settings SET value_string = %s, value_int = 1 WHERE name = 'login_notification'",
            (LoginNotif,))
    else:
        mycursor.execute(
            "UPDATE bancho_settings SET value_string = '', value_int = 0 WHERE name = 'login_notification'")

    if BanchoMan:
        mycursor.execute("UPDATE bancho_settings SET value_int = 1 WHERE name = 'bancho_maintenance'")
    else:
        mycursor.execute("UPDATE bancho_settings SET value_int = 0 WHERE name = 'bancho_maintenance'")

    mydb.commit()
    RAPLog(session["AccountId"], "modified the bancho settings")


def GetBmapInfo(id):
    """Gets beatmap info by beatmapset id."""
    mycursor.execute(
        "SELECT song_name, ar, difficulty_std, beatmapset_id, beatmap_id, ranked, mode FROM beatmaps WHERE beatmapset_id = %s",
        (id,))
    BMS_Data = mycursor.fetchall()

    if len(BMS_Data) == 0:  # not found
        return [{
            "SongName": "",
            "DiffName": "Not Found!",
            "Mode": 0,
            "Ar": 0,
            "Difficulty": 0,
            "BeatmapsetId": -1,
            "BeatmapId": -1,
            "Ranked": 0,
            "Cover": "https://debian.moe/static/files/nt_found.png"
        }]

    BeatmapList = []
    for beatmap in BMS_Data:
        titleData = beatmap[0].split("[")
        diffName = "[" + titleData[len(titleData) - 1]
        songName = beatmap[0].replace(" " + diffName, "")

        """modeImage = ""
        if beatmap[6] == 0:
            modeImage = "https://debian.moe/static/files/std.png"
        if beatmap[6] == 1:
            modeImage = "https://debian.moe/static/files/taiko.png"
        if beatmap[6] == 2:
            modeImage = "https://debian.moe/static/files/catch.png"
        if beatmap[6] == 3:
            modeImage = "https://debian.moe/static/files/mania.png"""""

        thing = {
            "SongName": songName,
            "DiffName": diffName,
            "Mode": beatmap[6],
            "Ar": str(beatmap[1]),
            "Difficulty": str(round(beatmap[2], 2)),
            "BeatmapsetId": str(beatmap[3]),
            "BeatmapId": str(beatmap[4]),
            "Ranked": beatmap[5],
            "Cover": f"https://assets.ppy.sh/beatmaps/{beatmap[3]}/covers/cover.jpg"
        }
        BeatmapList.append(thing)
    BeatmapList = sorted(BeatmapList, key=lambda i: i["Difficulty"])
    BeatmapList = sorted(BeatmapList, key=lambda i: i["Mode"])
    # assigning each bmap a number to be later used
    BMapNumber = 0
    for beatmap in BeatmapList:
        beatmap["BmapNumber"] = BMapNumber
        BMapNumber = BMapNumber + 1
    return BeatmapList


def HasPrivilege(UserID: int, ReqPriv=2):
    """Check if the person trying to access the page has perms to do it."""
    # 0 = no verification
    # 1 = Only registration required
    # 2 = RAP Access Required
    # 3 = Manage beatmaps required
    # 4 = manage settings required
    # 5 = Ban users required
    # 6 = Manage users required
    # 7 = View logs
    # 8 = RealistikPanel Nominate (feature not added yet)
    # 9 = RealistikPanel Nomination Accept (feature not added yet)
    # 10 = RealistikPanel Overwatch (feature not added yet)
    # 11 = Wipe account required
    # 12 = Kick users required
    # 13 = Manage Privileges
    # 14 = View RealistikPanel error/console logs
    # THIS TOOK ME SO LONG TO FIGURE OUT WTF
    NoPriv = 0
    UserNormal = 2 << 0
    AccessRAP = 2 << 2
    ManageUsers = 2 << 3
    BanUsers = 2 << 4
    SilenceUsers = 2 << 5
    WipeUsers = 2 << 6
    ManageBeatmaps = 2 << 7
    ManageServers = 2 << 8
    ManageSettings = 2 << 9
    ManageBetaKeys = 2 << 10
    ManageReports = 2 << 11
    ManageDocs = 2 << 12
    ManageBadges = 2 << 13
    ViewRAPLogs = 2 << 14
    ManagePrivileges = 2 << 15
    SendAlerts = 2 << 16
    ChatMod = 2 << 17
    KickUsers = 2 << 18
    PendingVerification = 2 << 19
    TournamentStaff = 2 << 20
    Caker = 2 << 21
    ViewTopScores = 2 << 22
    # RealistikPanel Specific Perms
    RPNominate = 2 << 23
    RPNominateAccept = 2 << 24
    RPOverwatch = 2 << 25
    RPErrorLogs = 2 << 26

    if ReqPriv == 0:  # dont use this like at all
        return True

    # gets users privilege
    try:
        mycursor.execute("SELECT privileges FROM users WHERE id = %s", (UserID,))
        Privilege = mycursor.fetchall()
        if len(Privilege) == 0:
            Privilege = 0
        else:
            Privilege = Privilege[0][0]
    except Exception:
        Privilege = 0

    if ReqPriv == 1:
        result = Privilege & UserNormal
    elif ReqPriv == 2:
        result = Privilege & AccessRAP
    elif ReqPriv == 3:
        result = Privilege & ManageBeatmaps
    elif ReqPriv == 4:
        result = Privilege & ManageSettings
    elif ReqPriv == 5:
        result = Privilege & BanUsers
    elif ReqPriv == 6:
        result = Privilege & ManageUsers
    elif ReqPriv == 7:
        result = Privilege & ViewRAPLogs
    elif ReqPriv == 8:
        result = Privilege & RPNominate
    elif ReqPriv == 9:
        result = Privilege & RPNominateAccept
    elif ReqPriv == 10:
        result = Privilege & RPOverwatch
    elif ReqPriv == 11:
        result = Privilege & WipeUsers
    elif ReqPriv == 12:
        result = Privilege & KickUsers
    elif ReqPriv == 13:
        result = Privilege & ManagePrivileges
    elif ReqPriv == 14:
        result = Privilege & RPErrorLogs

    if result >= 1:
        return True
    else:
        return False


def RankBeatmap(BeatmapNumber, BeatmapId, ActionName, session):
    """Ranks a beatmap"""
    # converts actions to numbers
    if ActionName == "Loved":
        ActionName = 5
    elif ActionName == "Ranked":
        ActionName = 2
    elif ActionName == "Unranked":
        ActionName = 0
    else:
        print(" Received alien input from rank. what?")
        return
    mycursor.execute("UPDATE beatmaps SET ranked = %s, ranked_status_freezed = 1 WHERE beatmap_id = %s LIMIT 1",
                     (ActionName, BeatmapId,))
    mycursor.execute(
        "UPDATE scores s JOIN (SELECT userid, MAX(score) maxscore FROM scores JOIN beatmaps ON scores.beatmap_md5 = beatmaps.beatmap_md5 WHERE beatmaps.beatmap_md5 = (SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = %s LIMIT 1) GROUP BY userid) s2 ON s.score = s2.maxscore AND s.userid = s2.userid SET completed = 3",
        (BeatmapId,))
    mydb.commit()
    Webhook(BeatmapId, ActionName, session)


def MapIdToMapsetID(mapID):
    json_url = urlopen("https://osu.ppy.sh/api/get_beatmaps?k=" + UserConfig["osuAPIkey"] + "&b=" + mapID)
    data = json.loads(json_url.read())
    if len(data) > 0:
        return data[0]["beatmapset_id"]
    else:
        return 0

def CheckDiffCount(mapSetID):
    json_url = urlopen("https://osu.ppy.sh/api/get_beatmaps?k=" + UserConfig["osuAPIkey"] + "&s=" + mapSetID)
    data = json.loads(json_url.read())
    return len(data)


def RankBeatmaps(mapSetID, data):
    """Ranks multiple beatmaps"""
    beatmapCount = round((len(data) - 2) / 4)

    for i in range(beatmapCount):
        rankStatus = 0
        if data["rankstatus-" + str(i)] == "Unranked":
            rankStatus = 0
        elif data["rankstatus-" + str(i)] == "Ranked":
            rankStatus = 2
        elif data["rankstatus-" + str(i)] == "Loved":
            rankStatus = 5
        mycursor.execute(
            "UPDATE beatmaps SET ranked = %s, rankedby = %s, ranked_status_freezed = 1 WHERE beatmap_id = %s LIMIT 1",
            (rankStatus, data["rankedby"], data["bmapid-" + str(i)],))
        mycursor.execute(
            "UPDATE scores s JOIN (SELECT userid, MAX(score) maxscore FROM scores JOIN beatmaps ON scores.beatmap_md5 = beatmaps.beatmap_md5 WHERE beatmaps.beatmap_md5 = (SELECT beatmap_md5 FROM beatmaps WHERE beatmap_id = %s LIMIT 1) GROUP BY userid) s2 ON s.score = s2.maxscore AND s.userid = s2.userid SET completed = 3",
            (data["bmapid-" + str(i)],))
        mydb.commit()

    BeatmapRankedWebhook(mapSetID, data, beatmapCount)


def BeatmapRankedWebhook(mapSetID, data, count):
    """Beatmap rank webhook."""
    if UserConfig["RankWebhook_std"] == "" or UserConfig["RankWebhook_taiko"] == "" or UserConfig[
        "RankWebhook_ctb"] == "" or UserConfig["RankWebhook_mania"] == "":
        print("No Webhook")
        return

    print(data)

    webhookArray = [[], [], [], []]

    for i in range(count):
        # sort items by mode.
        # webhookArray[mode][map index][ranked status/diff/map id]
        webhookArray[int(data["mode-" + str(i)])].append(
            [data["rankstatus-" + str(i)], data["diff-" + str(i)], data["bmapid-" + str(i)]])
    print("webhookArray : " + str(webhookArray))

    webhooks = [DiscordWebhook(url=UserConfig["RankWebhook_std"]), DiscordWebhook(url=UserConfig["RankWebhook_taiko"]),
                DiscordWebhook(url=UserConfig["RankWebhook_ctb"]), DiscordWebhook(url=UserConfig["RankWebhook_mania"])]

    embeds = [
        DiscordEmbed(title="<:osustd:700329507889872896> " + data["songname"],
                     description="Updated by " + data["rankedby"] + "\nㅤ", color=242424),
        DiscordEmbed(title="<:osutaiko:700329507852124281> " + data["songname"],
                     description="Updated by " + data["rankedby"] + "\nㅤ", color=242424),
        DiscordEmbed(title="<:osucatch:700329507936272444> " + data["songname"],
                     description="Updated by " + data["rankedby"] + "\nㅤ", color=242424),
        DiscordEmbed(title="<:osumania:700329508036673646> " + data["songname"],
                     description="Updated by " + data["rankedby"] + "\nㅤ", color=242424)
    ]

    for i in range(len(webhooks)):
        if len(webhookArray[i]) == 0:
            continue
        embeds[i].set_image(url="https://assets.ppy.sh/beatmaps/" + mapSetID + "/covers/cover.jpg")
        embeds[i].set_timestamp()
        mapsArray = [[], [], []]
        for j in range(len(webhookArray[i])):
            # sort items by ranked status.
            # mapsArray[ranked status][map index][diff/map id]
            if webhookArray[i][j][0] == "Unranked":
                mapsArray[0].append([webhookArray[i][j][1], webhookArray[i][j][2]])
            elif webhookArray[i][j][0] == "Ranked":
                mapsArray[1].append([webhookArray[i][j][1], webhookArray[i][j][2]])
            elif webhookArray[i][j][0] == "Loved":
                mapsArray[2].append([webhookArray[i][j][1], webhookArray[i][j][2]])
        print("mapsArray : " + str(mapsArray))
        embedValues = ["", "", ""]
        for j in range(len(mapsArray)):
            if len(mapsArray[j]) == 0:
                print("No maps for rank status " + str(j))
                continue
            for k in range(len(mapsArray[j])):
                embedValues[j] += "[" + mapsArray[j][k][0] + "](https://debian.moe/b/" + mapsArray[j][k][1] + ")\n"
        embeds[i].add_embed_field(name="Ranked",
                                  value=str(NumToEmojis(len(mapsArray[1]))) + "\n" + embedValues[1] + "ㅤ")
        embeds[i].add_embed_field(name="Loved",
                                  value=str(NumToEmojis(len(mapsArray[2]))) + "\n" + embedValues[2] + "ㅤ")
        embeds[i].add_embed_field(name="Unranked",
                                  value=str(NumToEmojis(len(mapsArray[0]))) + "\n" + embedValues[0] + "ㅤ")
        webhooks[i].add_embed(embeds[i])
        response = webhooks[i].execute()


def NumToEmojis(num):
    numbers = [int(i) for i in str(num)]
    textToReturn = ""
    for i in range(len(numbers)):
        if numbers[i] == 0:
            textToReturn += ":zero:"
        elif numbers[i] == 1:
            textToReturn += ":one:"
        elif numbers[i] == 2:
            textToReturn += ":two:"
        elif numbers[i] == 3:
            textToReturn += ":three:"
        elif numbers[i] == 4:
            textToReturn += ":four:"
        elif numbers[i] == 5:
            textToReturn += ":five:"
        elif numbers[i] == 6:
            textToReturn += ":six:"
        elif numbers[i] == 7:
            textToReturn += ":seven:"
        elif numbers[i] == 8:
            textToReturn += ":eight:"
        elif numbers[i] == 9:
            textToReturn += ":nine:"
    return textToReturn


def Webhook(BeatmapId, ActionName, session):
    """Beatmap rank webhook."""
    if UserConfig["EnableWebhook"] == 0:
        return

    headers = {'Content-Type': 'application/json'}
    mycursor.execute("SELECT song_name, beatmapset_id, mode FROM beatmaps WHERE beatmap_id = %s", (BeatmapId,))
    mapa = mycursor.fetchall()
    mode = mapa[2]
    mapa = mapa[0]
    if ActionName == 0:
        TitleText = "unranked :("
    if ActionName == 2:
        TitleText = "ranked!"
    if ActionName == 5:
        TitleText = "loved!"

    webhook = DiscordWebhook(url=UserConfig["RankWebhook"])  # creates default webhook
    if mode == 0 and UserConfig["RankWebhook_std"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_std"])
    if mode == 1 and UserConfig["RankWebhook_taiko"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_taiko"])
    if mode == 2 and UserConfig["RankWebhook_ctb"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_ctb"])
    if mode == 3 and UserConfig["RankWebhook_mania"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_mania"])

    # me trying to learn the webhook
    # EmbedJson = { #json to be sent to webhook
    #    "image" : f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg",
    #    "author" : {
    #        "icon_url" : f"https://a.debian.moe/{session['AccountId']}",
    #        "url" : f"https://debian.moe/b/{BeatmapId}",
    #        "name" : f"{mapa[0]} was just {TitleText}"
    #    },
    #    "description" : f"Ranked by {session['AccountName']}",
    #    "footer" : {
    #        "text" : "via RealistikPanel!"
    #    }
    # }
    # requests.post(URL, data=EmbedJson, headers=headers) #sends the webhook data
    embed = DiscordEmbed(description=f"Ranked by {session['AccountName']}",
                         color=242424)  # this is giving me discord.py vibes
    embed.set_author(name=f"{mapa[0]} was just {TitleText}", url=f"https://debian.moe/b/{BeatmapId}",
                     icon_url=f"https://a.debian.moe/{session['AccountId']}")
    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{mapa[1]}/covers/cover.jpg")
    webhook.add_embed(embed)
    print(" * Posting webhook!")
    webhook.execute()
    if ActionName == 0:
        Logtext = "unranked"
    if ActionName == 2:
        Logtext = "ranked"
    if ActionName == 5:
        Logtext = "loved"
    RAPLog(session["AccountId"], f"{Logtext} the beatmap {mapa[0]} ({BeatmapId})")


def RAPLog(UserID=999, Text="forgot to assign a text value :/"):
    """Logs to the RAP log."""
    Timestamp = round(time.time())
    # now we putting that in oh yea
    mycursor.execute("INSERT INTO rap_logs (userid, text, datetime, through) VALUES (%s, %s, %s, 'RealistikPanel!')",
                     (UserID, Text, Timestamp,))
    mydb.commit()


def checkpw(dbpassword, painpassword):
    """
    By: kotypey
    password checking...
    """

    result = hashlib.md5(painpassword.encode()).hexdigest().encode('utf-8')
    dbpassword = dbpassword.encode('utf-8')
    check = bcrypt.checkpw(result, dbpassword)

    return check


def SystemSettingsValues():
    """Fetches the system settings data."""
    mycursor.execute(
        "SELECT value_int, value_string FROM system_settings WHERE name = 'website_maintenance' OR name = 'game_maintenance' OR name = 'website_global_alert' OR name = 'website_home_alert' OR name = 'registrations_enabled'")
    SqlData = mycursor.fetchall()
    return {
        "webman": bool(SqlData[0][0]),
        "gameman": bool(SqlData[1][0]),
        "register": bool(SqlData[4][0]),
        "globalalert": SqlData[2][1],
        "homealert": SqlData[3][1]
    }


def ApplySystemSettings(DataArray, Session):
    """Applies system settings."""
    WebMan = DataArray[0]
    GameMan = DataArray[1]
    Register = DataArray[2]
    GlobalAlert = DataArray[3]
    HomeAlert = DataArray[4]

    # i dont feel like this is the right way to do this but eh
    if WebMan == "On":
        WebMan = 1
    else:
        WebMan = 0
    if GameMan == "On":
        GameMan = 1
    else:
        GameMan = 0
    if Register == "On":
        Register = 1
    else:
        Register = 0

    # SQL Queries
    mycursor.execute("UPDATE system_settings SET value_int = %s WHERE name = 'website_maintenance'", (WebMan,))
    mycursor.execute("UPDATE system_settings SET value_int = %s WHERE name = 'game_maintenance'", (GameMan,))
    mycursor.execute("UPDATE system_settings SET value_int = %s WHERE name = 'registrations_enabled'", (Register,))

    # if empty, disable
    if GlobalAlert != "":
        mycursor.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_global_alert'",
            (GlobalAlert,))
    else:
        mycursor.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_global_alert'")
    if HomeAlert != "":
        mycursor.execute(
            "UPDATE system_settings SET value_int = 1, value_string = %s WHERE name = 'website_home_alert'",
            (HomeAlert,))
    else:
        mycursor.execute(
            "UPDATE system_settings SET value_int = 0, value_string = '' WHERE name = 'website_home_alert'")

    mydb.commit()  # applies the changes


def IsOnline(AccountId: int):
    """Checks if given user is online."""
    Online = requests.get(url=f"{UserConfig['BanchoURL']}api/v1/isOnline?id={AccountId}").json()
    if Online["status"] == 200:
        return Online["result"]
    else:
        return False


def CalcPP(BmapID):
    """Sends request to letsapi to calc PP for beatmap id."""
    reqjson = requests.get(url=f"{UserConfig['LetsAPI']}v1/pp?b={BmapID}").json()
    return round(reqjson["pp"][0], 2)


def Unique(Alist):
    """Returns list of unique elements of list."""
    Uniques = []
    for x in Alist:
        if x not in Uniques:
            Uniques.append(x)
    return Uniques


def FetchUsers(page=0):
    """Fetches users for the users page."""
    # This is going to need a lot of patching up i can feel it
    Offset = UserConfig["PageSize"] * page  # for the page system to work
    mycursor.execute("SELECT id, username, privileges, allowed FROM users LIMIT %s OFFSET %s",
                     (UserConfig['PageSize'], Offset,))
    People = mycursor.fetchall()

    # gets list of all different privileges so an sql select call isnt ran per person
    AllPrivileges = []
    for person in People:
        AllPrivileges.append(person[2])
    UniquePrivileges = Unique(AllPrivileges)

    # How the privilege data will look
    # PrivilegeDict = {
    #    "234543": {
    #        "Name" : "Owner",
    #        "Privileges" : 234543,
    #        "Colour" : "success"
    #    }
    # }
    PrivilegeDict = {}
    # gets all priv info
    for Priv in UniquePrivileges:
        mycursor.execute("SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1", (Priv,))
        info = mycursor.fetchall()
        if len(info) == 0:
            PrivilegeDict[str(Priv)] = {
                "Name": f"Unknown ({Priv})",
                "Privileges": Priv,
                "Colour": "danger"
            }
        else:
            info = info[0]
            PrivilegeDict[str(Priv)] = {}
            PrivilegeDict[str(Priv)]["Name"] = info[0]
            PrivilegeDict[str(Priv)]["Privileges"] = Priv
            PrivilegeDict[str(Priv)]["Colour"] = info[1]
            if PrivilegeDict[str(Priv)]["Colour"] == "default" or PrivilegeDict[str(Priv)]["Colour"] == "":
                # stisla doesnt have a default button so ill hard-code change it to a warning
                PrivilegeDict[str(Priv)]["Colour"] = "warning"

    # Convierting user data into cool dicts
    # Structure
    # [
    #    {
    #        "Id" : 999,
    #        "Name" : "RealistikDash",
    #        "Privilege" : PrivilegeDict["234543"],
    #        "Allowed" : True
    #    }
    # ]
    Users = []
    for user in People:
        # country query
        mycursor.execute("SELECT country FROM users_stats WHERE id = %s", (user[0],))
        Country = mycursor.fetchall()
        if len(Country) == 0:
            Country = "XX"
        else:
            Country = Country[0][0]
        Dict = {
            "Id": user[0],
            "Name": user[1],
            "Privilege": PrivilegeDict[str(user[2])],
            "Country": Country
        }
        if user[3] == 1:
            Dict["Allowed"] = True
        else:
            Dict["Allowed"] = False
        Users.append(Dict)

    return Users


def GetUser(id):
    """Gets data for user. (universal)"""
    mycursor.execute("SELECT id, username, pp_std, country FROM users_stats WHERE id = %s LIMIT 1", (id,))
    User = mycursor.fetchall()
    if len(User) == 0:
        # if no one found
        return {
            "Id": 0,
            "Username": "Not Found",
            "pp": 0,
            "IsOnline": False,
            "Country": "GB"  # RULE BRITANNIA
        }
    User = User[0]
    return {
        "Id": User[0],
        "Username": User[1],
        "pp": User[2],
        "IsOnline": IsOnline(id),
        "Country": User[3]
    }


def UserData(id):
    """Gets data for user. (specialised for user edit page)"""
    Data = GetUser(id)
    mycursor.execute("SELECT userpage_content, user_color, username_aka FROM users_stats WHERE id = %s LIMIT 1",
                     (id,))  # Req 1
    Data1 = mycursor.fetchall()
    if len(Data1) == 0:  # check for stupid bugs THAT SOMEHOW BREAK THE ENTIRE PANEL LIEK WTF
        return False
    Data1 = Data1[0]
    mycursor.execute(
        "SELECT email, register_datetime, privileges, notes, donor_expire, silence_end, silence_reason FROM users WHERE id = %s LIMIT 1",
        (id,))
    Data2 = mycursor.fetchall()[0]
    # Fetches the IP
    mycursor.execute("SELECT ip FROM ip_user WHERE userid = %s LIMIT 1", (id,))
    try:
        Ip = mycursor.fetchall()
        if len(Ip) == 0:
            Ip = "0.0.0.0"
        else:
            Ip = Ip[0][0]
    except Exception:
        Ip = "0.0.0.0"
    # gets privilege name
    mycursor.execute("SELECT name FROM privileges_groups WHERE privileges = %s LIMIT 1", (Data2[2],))
    PrivData = mycursor.fetchall()
    if len(PrivData) == 0:
        PrivData = [[f"Unknown ({Data2[2]})"]]
    # adds new info to dict
    # I dont use the discord features from RAP so i didnt include the discord settings but if you complain enough ill add them
    Data["UserpageContent"] = Data1[0]
    Data["UserColour"] = Data1[1]
    Data["Aka"] = Data1[2]
    Data["Email"] = Data2[0]
    Data["RegisterTime"] = Data2[1]
    Data["Privileges"] = Data2[2]
    Data["Notes"] = Data2[3]
    Data["DonorExpire"] = Data2[4]
    Data["SilenceEnd"] = Data2[5]
    Data["SilenceReason"] = Data2[6]
    Data["Avatar"] = UserConfig["AvatarServer"] + str(id)
    Data["Ip"] = Ip
    Data["CountryFull"] = GetCFullName(Data["Country"])
    Data["PrivName"] = PrivData[0][0]

    Data["HasSupporter"] = Data["Privileges"] & 4
    Data["DonorExpireStr"] = TimeToTimeAgo(Data["DonorExpire"])

    # removing "None" from user page and admin notes
    if Data["Notes"] == None:
        Data["Notes"] = ""
    if Data["UserpageContent"] == None:
        Data["UserpageContent"] = ""
    return Data


def RAPFetch(page=1):
    """Fetches RAP Logs."""
    page = int(page) - 1  # makes sure is int and is in ok format
    Offset = UserConfig["PageSize"] * page
    mycursor.execute("SELECT * FROM rap_logs ORDER BY id DESC LIMIT %s OFFSET %s", (UserConfig['PageSize'], Offset,))
    Data = mycursor.fetchall()

    # Gets list of all users
    Users = []
    for dat in Data:
        if dat[1] not in Users:
            Users.append(dat[1])
    # gets all unique users so a ton of lookups arent made
    UniqueUsers = Unique(Users)

    # now we get basic data for each user
    UserDict = {}
    for user in UniqueUsers:
        UserData = GetUser(user)
        UserDict[str(user)] = UserData

    # log structure
    # [
    #    {
    #        "LogId" : 1337,
    #        "AccountData" : 1000,
    #        "Text" : "did a thing",
    #        "Via" : "RealistikPanel",
    #        "Time" : 18932905234
    #    }
    # ]
    LogArray = []
    for log in Data:
        # we making it into cool dicts
        # getting the acc data
        LogUserData = UserDict[str(log[1])]
        TheLog = {
            "LogId": log[0],
            "AccountData": LogUserData,
            "Text": log[2],
            "Time": TimestampConverter(log[3], 2),
            "Via": log[4]
        }
        LogArray.append(TheLog)
    return LogArray


def GetCFullName(ISO3166):
    """Gets the full name of the country provided."""
    Country = pycountry.countries.get(alpha_2=ISO3166)
    try:
        CountryName = Country.name
    except:
        CountryName = "Unknown"
    return CountryName


def GetPrivileges():
    """Gets list of privileges."""
    mycursor.execute("SELECT * FROM privileges_groups")
    priv = mycursor.fetchall()
    if len(priv) == 0:
        return []
    Privs = []
    for x in priv:
        Privs.append({
            "Id": x[0],
            "Name": x[1],
            "Priv": x[2],
            "Colour": x[3]
        })
    return Privs


def ApplyUserEdit(form, session):
    """Apples the user settings."""
    # getting variables from form
    UserId = form["userid"]
    Username = form["username"]
    Aka = form["aka"]
    Email = form["email"]
    Country = form["country"]
    UserPage = form["userpage"]
    Notes = form["notes"]
    Privilege = form["privilege"]
    # Creating safe username
    SafeUsername = Username.lower()
    SafeUsername.replace(" ", "_")

    # stop people ascending themselves
    # OriginalPriv = int(session["Privilege"])
    FromID = session["AccountId"]
    if int(UserId) == FromID:
        mycursor.execute("SELECT privileges FROM users WHERE id = %s", (FromID,))
        OriginalPriv = mycursor.fetchall()
        if len(OriginalPriv) == 0:
            return
        OriginalPriv = OriginalPriv[0][0]
        if int(Privilege) > OriginalPriv:
            return

    # Badges
    BadgeList = [int(form["Badge1"]), int(form["Badge2"]), int(form["Badge3"]), int(form["Badge4"]),
                 int(form["Badge5"]), int(form["Badge6"])]
    SetUserBadges(UserId, BadgeList)
    # SQL Queries
    mycursor.execute(
        "UPDATE users SET email = %s, notes = %s, username = %s, username_safe = %s, privileges=%s WHERE id = %s",
        (Email, Notes, Username, SafeUsername, Privilege, UserId,))
    mycursor.execute(
        "UPDATE users_stats SET country = %s, userpage_content = %s, username_aka = %s, username = %s WHERE id = %s",
        (Country, UserPage, Aka, Username, UserId,))
    if UserConfig["HasRelax"]:
        mycursor.execute("UPDATE rx_stats SET country = %s, username_aka = %s, username = %s WHERE id = %s",
                         (Country, Aka, Username, UserId,))
    mydb.commit()


def ModToText(mod: int):
    """Converts mod enum to cool string."""
    # mod enums
    Mods = ""
    if mod == 0:
        return ""
    else:
        # adding mod names to str
        # they use bitwise too just like the perms
        if mod & 1:
            Mods += "NF"
        if mod & 2:
            Mods += "EZ"
        if mod & 4:
            Mods += "NV"
        if mod & 8:
            Mods += "HD"
        if mod & 16:
            Mods += "HR"
        if mod & 32:
            Mods += "SD"
        if mod & 64:
            Mods += "DT"
        if mod & 128:
            Mods += "RX"
        if mod & 256:
            Mods += "HT"
        if mod & 512:
            Mods += "NC"
        if mod & 1024:
            Mods += "FL"
        if mod & 2048:
            Mods += "AP"
        if mod & 4096:
            Mods += "SO"
        if mod & 8192:
            Mods += "RX"
        if mod & 16384:
            Mods += "PF"
        if mod & 32768:
            Mods += "K4"
        if mod & 65536:
            Mods += "K5"
        if mod & 131072:
            Mods += "K6"
        if mod & 262144:
            Mods += "K7"
        if mod & 524288:
            Mods += "K8"
        if mod & 1015808:
            Mods += "KM"  # idk what this is
        if mod & 1048576:
            Mods += "FI"
        if mod & 2097152:
            Mods += "RM"
        if mod & 4194304:
            Mods += "LM"
        if mod & 16777216:
            Mods += "K9"
        if mod & 33554432:
            Mods += "KX"  # key 10 but 2 char. might change to k10
        if mod & 67108864:
            Mods += "K1"
        if mod & 134217728:
            Mods += "K2"
        if mod & 268435456:
            Mods += "K3"
        return Mods


def WipeAccount(AccId):
    """Wipes the account with the given id."""
    mycursor.execute("DELETE FROM scores WHERE userid = %s", (AccId,))
    r.publish("peppy:disconnect", json.dumps({  # lets the user know what is up
        "userID": id,
        "reason": f"Your account has been wiped! F"
    }))
    if UserConfig["HasRelax"]:
        mycursor.execute("DELETE FROM scores_relax WHERE userid = %s", (AccId))
    # now we reset stats... thats a bit of a query if i say so myself
    mycursor.execute(
        "UPDATE users_stats SET ranked_score_std = 0, playcount_std = 0, total_score_std = 0, replays_watched_std = 0, ranked_score_taiko = 0, playcount_taiko = 0, total_score_taiko = 0, replays_watched_taiko = 0, ranked_score_ctb = 0, playcount_ctb = 0, total_score_ctb = 0, replays_watched_ctb = 0, ranked_score_mania = 0, playcount_mania = 0, total_score_mania = 0, replays_watched_mania = 0, total_hits_std = 0, total_hits_taiko = 0, total_hits_ctb = 0, total_hits_mania = 0, unrestricted_pp = 0, level_std = 0, level_taiko = 0, level_ctb = 0, level_mania = 0, playtime_std = 0, playtime_taiko = 0, playtime_ctb = 0, playtime_mania = 0, avg_accuracy_std = 0.000000000000, avg_accuracy_taiko = 0.000000000000, avg_accuracy_ctb = 0.000000000000, avg_accuracy_mania = 0.000000000000, pp_std = 0, pp_taiko = 0, pp_ctb = 0, pp_mania = 0 WHERE id = %s",
        (AccId,))
    if UserConfig["HasRelax"]:
        mycursor.execute(
            "UPDATE users_stats SET ranked_score_std = 0, playcount_std = 0, total_score_std = 0, replays_watched_std = 0, ranked_score_taiko = 0, playcount_taiko = 0, total_score_taiko = 0, replays_watched_taiko = 0, ranked_score_ctb = 0, playcount_ctb = 0, total_score_ctb = 0, replays_watched_ctb = 0, ranked_score_mania = 0, playcount_mania = 0, total_score_mania = 0, replays_watched_mania = 0, total_hits_std = 0, total_hits_taiko = 0, total_hits_ctb = 0, total_hits_mania = 0, unrestricted_pp = 0, level_std = 0, level_taiko = 0, level_ctb = 0, level_mania = 0, playtime_std = 0, playtime_taiko = 0, playtime_ctb = 0, playtime_mania = 0, avg_accuracy_std = 0.000000000000, avg_accuracy_taiko = 0.000000000000, avg_accuracy_ctb = 0.000000000000, avg_accuracy_mania = 0.000000000000, pp_std = 0, pp_taiko = 0, pp_ctb = 0, pp_mania = 0 WHERE id = %s",
            (AccId,))
    mydb.commit()


def ResUnTrict(id: int):
    """Restricts or unrestricts account yeah."""
    mycursor.execute("SELECT privileges FROM users WHERE id = %s", (id,))
    Privilege = mycursor.fetchall()
    if len(Privilege) == 0:
        return
    Privilege = Privilege[0][0]
    if Privilege == 2:  # if restricted
        TimeBan = round(time.time())
        mycursor.execute("UPDATE users SET privileges = 3, ban_datetime = 0 WHERE id = %s", (id,))  # unrestricts
        TheReturn = False
    else:
        r.publish("peppy:disconnect", json.dumps({  # lets the user know what is up
            "userID": id,
            "reason": f"Your account has been restricted! Check with staff to see what's up."
        }))
        TimeBan = round(time.time())
        mycursor.execute("UPDATE users SET privileges = 2, ban_datetime = %s WHERE id = %s",
                         (TimeBan, id,))  # restrict em bois
        RemoveFromLeaderboard(id)
        TheReturn = True
    UpdateBanStatus(id)
    mydb.commit()
    return TheReturn


def BanUser(id: int):
    """User go bye bye!"""
    mycursor.execute("SELECT privileges FROM users WHERE id = %s", (id,))
    Privilege = mycursor.fetchall()
    Timestamp = round(time.time())
    if len(Privilege) == 0:
        return
    Privilege = Privilege[0][0]
    if Privilege == 0:  # if already banned
        mycursor.execute("UPDATE users SET privileges = 3, ban_datetime = '0' WHERE id = %s", (id,))
        TheReturn = False
    else:
        mycursor.execute("UPDATE users SET privileges = 0, ban_datetime = %s WHERE id = %s", (Timestamp, id,))
        RemoveFromLeaderboard(id)
        r.publish("peppy:disconnect", json.dumps({  # lets the user know what is up
            "userID": id,
            "reason": f"You have been banned from {UserConfig['ServerName']}. You will not be missed."
        }))
        TheReturn = True
    UpdateBanStatus(id)
    mydb.commit()
    return TheReturn


def ClearHWID(id: int):
    """Clears the HWID matches for provided acc."""
    mycursor.execute("DELETE FROM hw_user WHERE userid = %s", (id,))
    mydb.commit()


def DeleteAccount(id: int):
    """Deletes the account provided. Press F to pay respects."""
    r.publish("peppy:disconnect", json.dumps({  # lets the user know what is up
        "userID": id,
        "reason": f"You have been deleted from {UserConfig['ServerName']}. Bye!"
    }))
    # NUKE. BIG NUKE.
    mycursor.execute("DELETE FROM scores WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM users WHERE id = %s", (id,))
    mycursor.execute("DELETE FROM 2fa WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM 2fa_telegram WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM 2fa_totp WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM beatmaps_rating WHERE user_id = %s", (id,))
    mycursor.execute("DELETE FROM comments WHERE user_id = %s", (id,))
    # mycursor.execute("DELETE FROM discord_roles WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM ip_user WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM profile_backgrounds WHERE uid = %s", (id,))
    mycursor.execute("DELETE FROM rank_requests WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM reports WHERE to_uid = %s OR from_uid = %s", (id, id,))
    mycursor.execute("DELETE FROM remember WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM tokens WHERE user = %s", (id,))
    mycursor.execute("DELETE FROM remember WHERE userid = %s", (id,))
    mycursor.execute("DELETE FROM users_achievements WHERE user_id = %s", (id,))
    mycursor.execute("DELETE FROM users_beatmap_playcount WHERE user_id = %s", (id,))
    mycursor.execute("DELETE FROM users_relationships WHERE user1 = %s OR user2 = %s", (id, id,))
    mycursor.execute("DELETE FROM user_badges WHERE user = %s", (id,))
    mycursor.execute("DELETE FROM user_clans WHERE user = %s", (id,))
    if UserConfig["HasRelax"]:
        mycursor.execute("DELETE FROM scores_relax WHERE userid = %s", (id,))
    mydb.commit()


def BanchoKick(id: int, reason):
    """Kicks the user from Bancho."""
    r.publish("peppy:disconnect", json.dumps({  # lets the user know what is up
        "userID": id,
        "reason": reason
    }))


def FindWithIp(Ip):
    """Gets array of users."""
    # fetching user id of person with given ip
    mycursor.execute("SELECT userid, ip FROM ip_user WHERE ip = %s", (Ip,))
    UserTruple = mycursor.fetchall()
    # turning the data into array with ids
    UserArray = []
    for x in UserTruple:
        ListToAdd = [x[0], x[1]]  # so ip is present for later use
        UserArray.append(ListToAdd)
    UserDataArray = []  # this will have the dicts
    for User in UserArray:
        if len(User) != 0:
            UserData = GetUser(User[0])
            UserData["Ip"] = User[1]
            UserDataArray.append(UserData)
        # lets take a second here to appreciate my naming scheme
    return UserDataArray


def PlayStyle(Enum: int):
    """Returns array of playstyles."""
    # should be similar to privileges (it is)
    Styles = []
    # Play style enums
    Mouse = 1 << 0
    Tablet = 1 << 1
    Keyboard = 1 << 2
    Touchscreen = 1 << 3
    # Nice ones ripple
    Spoon = 1 << 4
    LeapMotion = 1 << 5
    OculusRift = 1 << 6
    Dick = 1 << 7
    Eggplant = 1 << 8

    # if statement time
    if Enum & Mouse >= 1:
        Styles.append("Mouse")
    if Enum & Tablet >= 1:
        Styles.append("Tablet")
    if Enum & Keyboard >= 1:
        Styles.append("Keyboard")
    if Enum & Touchscreen >= 1:
        Styles.append("Touchscreen")
    if Enum & Spoon >= 1:
        Styles.append("Spoon")
    if Enum & LeapMotion >= 1:
        Styles.append("Leap Motion")
    if Enum & OculusRift >= 1:
        Styles.append("Oculus Rift")
    if Enum & Dick >= 1:
        Styles.append("Dick")
    if Enum & Eggplant >= 1:
        Styles.append("Eggplant")

    return Styles


def PlayerCountCollection(loop=True):
    """Designed to be ran as thread. Grabs player count every set interval and puts in array."""
    while loop:
        CurrentCount = int(r.get("ripple:online_users").decode("utf-8"))
        PlayerCount.append(CurrentCount)
        time.sleep(UserConfig["UserCountFetchRate"] * 60)
        # so graph doesnt get too huge
        if len(PlayerCount) > 40:
            PlayerCount.pop(PlayerCount[0])
    if not loop:
        CurrentCount = int(r.get("ripple:online_users").decode("utf-8"))
        PlayerCount.append(CurrentCount)
        time.sleep(UserConfig["UserCountFetchRate"] * 60)


def DashActData():
    """Returns data for dash graphs."""
    Data = {}
    Data["PlayerCount"] = json.dumps(PlayerCount)  # string for easier use in js

    # getting time intervals
    PrevNum = 0
    IntervalList = []
    for x in PlayerCount:
        IntervalList.append(str(PrevNum) + "m")
        PrevNum += UserConfig["UserCountFetchRate"]

    IntervalList.reverse()
    Data["IntervalList"] = json.dumps(IntervalList)
    return Data


def GiveSupporter(AccountID: int, Duration=1):
    """Gives the target user supporter.
    Args:
        AccountID (int): The account id of the target user.
        Duration (int): The time (in months) that the supporter rank should last
    """  # messing around with docstrings
    # checking if person already has supporter
    # also i believe there is a way better to do this, i am tired and may rewrite this and lower the query count
    mycursor.execute("SELECT privileges FROM users WHERE id = %s LIMIT 1", (AccountID,))
    CurrentPriv = mycursor.fetchall()[0][0]
    if CurrentPriv & 4:
        # already has supporter, extending
        mycursor.execute("SELECT donor_expire FROM users WHERE id = %s", (AccountID,))
        ToEnd = mycursor.execute()[0][0]
        ToEnd += 2.628e+6 * Duration
        mycursor.execute("UPDATE users SET donor_expire = %s WHERE id=%s", (ToEnd, AccountID,))
        mydb.commit()
    else:
        EndTimestamp = round(time.time()) + (2.628e+6 * Duration)
        CurrentPriv += 4  # adding donor perms
        mycursor.execute("UPDATE users SET privileges = %s, donor_expire = %s WHERE id = %s",
                         (CurrentPriv, EndTimestamp, AccountID,))
        mydb.commit()


def RemoveSupporter(AccountID: int):
    """Removes supporter from the target user."""
    mycursor.execute("SELECT privileges FROM users WHERE id = %s LIMIT 1", (AccountID,))
    CurrentPriv = mycursor.fetchall()[0][0]
    # checking if they dont have it so privs arent messed up
    if CurrentPriv & 4:
        return
    CurrentPriv -= 4
    mycursor.execute("UPDATE users SET privileges = %s, donor_expire = 0 WHERE id = %s", (CurrentPriv, AccountID,))


def GetBadges():
    """Gets all the badges."""
    mycursor.execute("SELECT * FROM badges")
    Data = mycursor.fetchall()
    Badges = []
    for badge in Data:
        Badges.append({
            "Id": badge[0],
            "Name": badge[1],
            "Icon": badge[2]
        })
    return Badges


def DeleteBadge(BadgeId: int):
    """"Delets the badge with the gived id."""
    mycursor.execute("DELETE FROM badges WHERE id = %s", (BadgeId,))
    mydb.commit()


def GetBadge(BadgeID: int):
    """Gets data of given badge."""
    mycursor.execute("SELECT * FROM badges WHERE id = %s LIMIT 1", (BadgeID,))
    BadgeData = mycursor.fetchall()[0]
    return {
        "Id": BadgeData[0],
        "Name": BadgeData[1],
        "Icon": BadgeData[2]
    }


def SaveBadge(form):
    """Saves the edits done to the badge."""
    BadgeID = form["badgeid"]
    BadgeName = form["name"]
    BadgeIcon = form["icon"]
    mycursor.execute("UPDATE badges SET name = %s, icon = %s WHERE id = %s", (BadgeName, BadgeIcon, BadgeID,))
    mydb.commit()


def ParseReplay(replay):
    """Parses replay and returns data in dict."""
    Replay = parse_replay_file(replay)
    return {
        # "GameMode" : Replay.game_mode, #commented until enum sorted out
        "GameVersion": Replay.game_version,
        "BeatmapHash": Replay.beatmap_hash,
        "Player": Replay.player_name,
        "ReplayHash": Replay.replay_hash,
        "300s": Replay.number_300s,
        "100s": Replay.number_100s,
        "50s": Replay.number_50s,
        "Gekis": Replay.gekis,
        "Katus": Replay.katus,
        "Misses": Replay.misses,
        "Score": Replay.score,
        "Combo": Replay.max_combo,
        "IsPC": Replay.is_perfect_combo,
        "Mods": Replay.mod_combination,
        "Timestamp": Replay.timestamp,
        "LifeGraph": Replay.life_bar_graph,
        "ReplayEvents": Replay.play_data  # useful for recreating the replay
    }


def CreateBadge():
    """Creates empty badge."""
    mycursor.execute("INSERT INTO badges (name, icon) VALUES ('New Badge', '')")
    mydb.commit()
    # checking the ID
    mycursor.execute("SELECT id FROM badges ORDER BY id DESC LIMIT 1")
    return mycursor.fetchall()[0][0]


def GetPriv(PrivID: int):
    """Gets the priv data from ID."""
    mycursor.execute("SELECT * FROM privileges_groups WHERE id = %s", (PrivID,))
    Priv = mycursor.fetchall()[0]
    return {
        "Id": Priv[0],
        "Name": Priv[1],
        "Privileges": Priv[2],
        "Colour": Priv[3]
    }


def DelPriv(PrivID: int):
    """Deletes a privilege group."""
    mycursor.execute("DELETE FROM privileges_groups WHERE id = %s", (PrivID,))
    mydb.commit()


def UpdatePriv(Form):
    """Updates the privilege from form."""
    # Get previous privilege number
    mycursor.execute("SELECT privileges FROM privileges_groups WHERE id = %s", (Form['id'],))
    PrevPriv = mycursor.fetchall()[0][0]
    # Update group
    mycursor.execute("UPDATE privileges_groups SET name = %s, privileges = %s, color = %s WHERE id = %s LIMIT 1",
                     (Form['name'], Form['privilege'], Form['colour'], Form['id']))
    # update privs for users
    mycursor.execute("UPDATE users SET privileges = REPLACE(privileges, %s, %s)", (PrevPriv, Form['privilege'],))
    mydb.commit()


def GetMostPlayed():
    """Gets the beatmap with the highest playcount."""
    mycursor.execute(
        "SELECT beatmap_id, song_name, beatmapset_id, playcount FROM beatmaps ORDER BY playcount DESC LIMIT 1")
    Beatmap = mycursor.fetchall()[0]
    return {
        "BeatmapId": Beatmap[0],
        "SongName": Beatmap[1],
        "Cover": f"https://assets.ppy.sh/beatmaps/{Beatmap[2]}/covers/cover.jpg",
        "Playcount": Beatmap[3]
    }


def DotsToList(Dots: str):
    """Converts a comma array (like the one ripple uses for badges) to a Python list."""
    return Dots.split(",")


def ListToDots(List: list):
    """Converts Python list to comma array."""
    Result = ""
    for part in List:
        Result += str(part) + ","
    return Result[:-1]


def GetUserBadges(AccountID: int):
    """Gets badges of a user and returns as list."""
    mycursor.execute("SELECT badge FROM user_badges WHERE user = %s", (AccountID,))
    Badges = []
    SQLBadges = mycursor.fetchall()
    for badge in SQLBadges:
        Badges.append(badge[0])

    # so we dont run into errors where people have no/less than 6 badges
    while len(Badges) != 6:
        Badges.append(0)
    return Badges


def SetUserBadges(AccountID: int, Badges: list):
    """Sets badge list to account."""
    """ Realised flaws with this approach
    CurrentBadges = GetUserBadges(AccountID) # so it knows which badges to keep
    ItemFor = 0
    for Badge in Badges:
        if not Badge == CurrentBadges[ItemFor]: #if its not the same
            mycursor.execute("DELETE FROM user_badges WHERE")
        ItemFor += 1
    """
    # This might not be the best and most efficient way but its all ive come up with in my application of user badges
    mycursor.execute("DELETE FROM user_badges WHERE user = %s", (AccountID,))  # deletes all existing badges
    for Badge in Badges:
        if Badge != 0 and Badge != 1:  # so we dont add empty badges
            mycursor.execute("INSERT INTO user_badges (user, badge) VALUES (%s, %s)", (AccountID, Badge,))
    mydb.commit()


def GetLog():
    """Gets the newest x (userconfig page size) entries in the log."""

    with open("realistikpanel.log") as Log:
        Log = json.load(Log)

    Log = Log[-UserConfig["PageSize"]:]
    Log.reverse()  # still wondering why it doesnt return the reversed list and instead returns none
    LogNr = 0
    # format the timestamps
    for log in Log:
        log["FormatDate"] = TimestampConverter(log["Timestamp"])
        Log[LogNr] = log
        LogNr += 1
    return Log


def GetBuild():
    """Gets the build number of the current version of RealistikPanel."""
    with open("buildinfo.json") as file:
        BuildInfo = json.load(file)
    return BuildInfo["version"]


def UpdateUserStore(Username: str):
    """Updates the user info stored in rpusers.json or creates the file."""
    if not os.path.exists("rpusers.json"):
        # if doesnt exist
        with open("rpusers.json", 'w') as json_file:
            json.dump({}, json_file, indent=4)

    # gets current log
    with open("rpusers.json", "r") as Log:
        Store = json.load(Log)

    Store[Username] = {
        "Username": Username,
        "LastLogin": round(time.time()),
        "LastBuild": GetBuild()
    }

    with open("rpusers.json", 'w') as json_file:
        json.dump(Store, json_file, indent=4)

    # Updating cached store
    CachedStore[Username] = {
        "Username": Username,
        "LastLogin": round(time.time()),
        "LastBuild": GetBuild()
    }


def GetUserStore(Username: str):
    """Gets user info from the store."""
    with open("rpusers.json", "r") as Log:
        Store = json.load(Log)

    if Username in list(Store.keys()):
        return Store[Username]
    else:
        return {
            "Username": Username,
            "LastLogin": round(time.time()),
            "LastBuild": 0
        }


def GetUserID(Username: str):
    """Gets user id from username."""
    mycursor.execute("SELECT id FROM users WHERE username LIKE %s LIMIT 1", (Username,))
    Data = mycursor.fetchall()
    if len(Data) == 0:
        return 0
    return Data[0][0]


def GetStore():
    """Returns user store as list."""
    with open("rpusers.json", "r") as RPUsers:
        Store = json.load(RPUsers)

    TheList = []
    for x in list(Store.keys()):
        # timeago - bit of an afterthought so sorry for weird implementation
        Store[x]["Timeago"] = TimeToTimeAgo(Store[x]["LastLogin"])
        # Gets User id
        Store[x]["Id"] = GetUserID(x)
        TheList.append(Store[x])

    return TheList


def SplitList(TheList: list):
    """Splits list into 2 halves (thanks stackoverflow)."""
    length = len(TheList)
    return [TheList[i * length // 2: (i + 1) * length // 2]
            for i in range(2)]


def TimeToTimeAgo(Timestamp: int):
    """Converts a seconds timestamp to a timeago string."""
    DTObj = datetime.datetime.fromtimestamp(Timestamp)
    CurrentTime = datetime.datetime.now()
    return timeago.format(DTObj, CurrentTime)


def RemoveFromLeaderboard(UserID: int):
    """Removes the user from leaderboards."""
    Modes = ["std", "ctb", "mania", "taiko"]
    for mode in Modes:
        # redis for each mode
        r.zrem(f"ripple:leaderboard:{mode}", UserID)
        if UserConfig["HasRelax"]:
            # removes from relax leaderboards
            r.zrem(f"ripple:leaderboard_relax:{mode}", UserID)

        # removing from country leaderboards
        mycursor.execute("SELECT country FROM users_stats WHERE id = %s LIMIT 1", (UserID,))
        Country = mycursor.fetchall()[0][0]
        if Country != "XX":  # check if the country is not set
            r.zrem(f"ripple:leaderboard:{mode}:{Country}", UserID)
            if UserConfig["HasRelax"]:
                r.zrem(f"ripple:leaderboard_relax:{mode}:{Country}", UserID)


def UpdateBanStatus(UserID: int):
    """Updates the ban statuses in bancho."""
    r.publish("peppy:ban", UserID)


def CacheAllDiffs(BeatmapSet: int):
    """Fecth All difficulties from osu!API and update DB"""
    beatmapSetData_url = urlopen(
        "https://osu.ppy.sh/api/get_beatmaps?k=" + UserConfig["osuAPIkey"] + "&s=" + BeatmapSet)
    beatmapSetData = json.loads(beatmapSetData_url.read())

    for i in range(len(beatmapSetData)):
        frozen = mycursor.execute("SELECT ranked_status_freezed FROM beatmaps WHERE beatmap_id = %s LIMIT 1",
                                  beatmapSetData[0]["beatmap_id"]).fetchAll()
        params = [
            beatmapSetData[i]["beatmap_id"],
            BeatmapSet,
            beatmapSetData[i]["file_md5"],
            beatmapSetData[i]["title"],
            beatmapSetData[i]["diff_approach"],
            beatmapSetData[i]["diff_overall"],
            beatmapSetData[i]["fi"],
        ]
        if frozen == None:
            mycursor.execute("INSERT INTO beatmaps (id, beatmap_id, beatmapset_id, beatmap_md5, song_name, ar, od, "
                             "difficulty_std, difficulty_taiko, difficulty_ctb, difficulty_mania, max_combo, hit_length,"
                             "bpm, ranked, latest_update, ranked_status_freezed, artist, creator, title, version,"
                             "cs, hp, mode)"
                             "VALUES (NULL, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                             params)

    print(beatmapSetData[0]["beatmap_id"])


"""def SetBMAPSetStatus(BeatmapSet: int, Staus: int, session):
    """"""Sets status for all beatmaps in beatmapset.""""""
    mycursor.execute(
        "UPDATE beatmaps SET rankedby = %s ,ranked = %s, ranked_status_freezed = 1 WHERE beatmapset_id = %s",
        (session['AccountName'], Staus, BeatmapSet,))
    mydb.commit()

    if UserConfig["EnableWebhook"] == 0:
        return

    # getting status text
    if Staus == 0:
        TitleText = "unranked"
    elif Staus == 2:
        TitleText = "ranked"
    elif Staus == 5:
        TitleText = "loved"

    mycursor.execute("SELECT song_name, beatmap_id FROM beatmaps WHERE beatmapset_id = %s LIMIT 1", (BeatmapSet,))
    MapData = mycursor.fetchall()[0]
    # Getting bmap name without diff
    BmapName = MapData[0].split("[")[0]  # ¯\_(ツ)_/¯ might work

    mycursor.execute("SELECT mode FROM beatmaps WHERE beatmapset_id = %s", (BeatmapSet,))
    # webhook, didnt use webhook function as it was too adapted for single map webhook
    # webhook = DiscordWebhook(url=UserConfig["Webhook"])
    webhook = DiscordWebhook(url=UserConfig["RankWebhook"])  # creates default webhook
    if mode == 0 and UserConfig["RankWebhook_std"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_std"])
    if mode == 1 and UserConfig["RankWebhook_taiko"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_taiko"])
    if mode == 2 and UserConfig["RankWebhook_ctb"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_ctb"])
    if mode == 3 and UserConfig["RankWebhook_mania"] != "":
        webhook = DiscordWebhook(url=UserConfig["RankWebhook_mania"])

    embed = DiscordEmbed(description=f"Ranked by {session['AccountName']}", color=242424)
    embed.set_author(name=f"{BmapName} was just {TitleText}.", url=f"https://debian.moe/b/{MapData[1]}",
                     icon_url=f"https://a.debian.moe/{session['AccountId']}")  # will rank to random diff but yea
    embed.set_footer(text="via RealistikPanel!")
    embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{BeatmapSet}/covers/cover.jpg")
    webhook.add_embed(embed)
    print(" * Posting webhook!")
    webhook.execute()"""


def FindUserByUsername(User: str, Page):
    """Finds user by their username OR email."""
    # calculating page offsets
    Offset = UserConfig["PageSize"] * (Page - 1)
    # checking if its an email
    Split = User.split("@")
    if len(Split) == 2 and "." in Split[
        1]:  # if its an email, 2nd check makes sure its an email and not someone trying to be A E S T H E T I C
        mycursor.execute("SELECT id, username, privileges, allowed FROM users WHERE email LIKE %s LIMIT %s OFFSET %s", (
            User, UserConfig["PageSize"], Offset,))  # i will keep the like statement unless it causes issues
    else:  # its a username
        User = f"%{User}%"  # for sql to treat is as substring
        mycursor.execute(
            "SELECT id, username, privileges, allowed FROM users WHERE username LIKE %s LIMIT %s OFFSET %s",
            (User, UserConfig["PageSize"], Offset,))
    Users = mycursor.fetchall()
    if len(Users) > 0:
        PrivilegeDict = {}
        AllPrivileges = []
        for person in Users:
            AllPrivileges.append(person[2])
        UniquePrivileges = Unique(AllPrivileges)
        # gets all priv info (copy pasted from get users as it is based on same infestructure)
        for Priv in UniquePrivileges:
            mycursor.execute("SELECT name, color FROM privileges_groups WHERE privileges = %s LIMIT 1", (Priv,))
            info = mycursor.fetchall()
            if len(info) == 0:
                PrivilegeDict[str(Priv)] = {
                    "Name": f"Unknown ({Priv})",
                    "Privileges": Priv,
                    "Colour": "danger"
                }
            else:
                info = info[0]
                PrivilegeDict[str(Priv)] = {}
                PrivilegeDict[str(Priv)]["Name"] = info[0]
                PrivilegeDict[str(Priv)]["Privileges"] = Priv
                PrivilegeDict[str(Priv)]["Colour"] = info[1]
                if PrivilegeDict[str(Priv)]["Colour"] == "default" or PrivilegeDict[str(Priv)]["Colour"] == "":
                    # stisla doesnt have a default button so ill hard-code change it to a warning
                    PrivilegeDict[str(Priv)]["Colour"] = "warning"

        TheUsersDict = []
        for yuser in Users:
            # country query
            mycursor.execute("SELECT country FROM users_stats WHERE id = %s", (yuser[0],))
            Country = mycursor.fetchall()[0][0]
            Dict = {
                "Id": yuser[0],
                "Name": yuser[1],
                "Privilege": PrivilegeDict[str(yuser[2])],
                "Country": Country
            }
            if yuser[3] == 1:
                Dict["Allowed"] = True
            else:
                Dict["Allowed"] = False
            TheUsersDict.append(Dict)

        return TheUsersDict
    else:
        return []


def UpdateCachedStore():  # not used for now
    """Updates the data in the cached user store."""
    UpToDateStore = GetStore()
    for User in UpToDateStore:
        CachedStore[User["Username"]] = {}
        for Key in list(User.keys()):
            CachedStore[User["Username"]][Key] = User[Key]


def GetCachedStore(Username: str):
    if Username in list(CachedStore.keys()):
        return CachedStore[Username]
    else:
        return {
            "Username": Username,
            "LastLogin": round(time.time()),
            "LastBuild": 0
        }


def CreateBcrypt(Password: str):
    """Creates hashed password using the hashing methods of Ripple."""
    MD5Password = hashlib.md5(Password.encode('utf-8')).hexdigest()
    BHashed = bcrypt.hashpw(MD5Password.encode("utf-8"), bcrypt.gensalt(10))
    return BHashed.decode()


def ChangePassword(AccountID: int, NewPassword: str):
    """Changes the password of a user with given AccID """
    BCrypted = CreateBcrypt(NewPassword)
    mycursor.execute("UPDATE users SET password_md5 = %s WHERE id = %s", (BCrypted, AccountID,))
    mydb.commit()


def ChangePWForm(form):  # this function may be unnecessary but ehh
    """Handles the change password POST request."""
    ChangePassword(form["accid"], form["newpass"])


def GiveSupporterForm(form):
    GiveSupporter(form["accid"], int(form["time"]))
