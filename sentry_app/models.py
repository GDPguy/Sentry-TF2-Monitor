class PlayerInstance:
    def __init__(self, userid, name, ping, steamid, kills, deaths, player_type=None, notes=None, team=None):
        self.userid = userid
        self.name = name
        self.ping = ping
        self.steamid = steamid
        self.kills = kills
        self.deaths = deaths
        self.player_type = player_type
        self.notes = notes
        self.team = team
