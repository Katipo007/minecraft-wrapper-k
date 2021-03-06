# coding=utf-8
from __future__ import print_function
import traceback

NAME = "WorldEdit"
ID = "com.benbaptist.plugins.fake-worldedit"
VERSION = (0, 2)
AUTHOR = "Ben Baptist"
WEBSITE = "http://wrapper.benbaptist.com/"
SUMMARY = "Edit the world with this WorldEdit clone. (Original WorldEdit for Bukkit by sk89q)"
DESCRIPTION = """This is a clone of the WorldEdit plugin by sk89q on Bukkit for Wrapper.py.
It contains most of the same syntax, though not all of the commands have been implemented just yet."""


class Main:
    def __init__(self, api, log):
        self.api = api
        self.minecraft = api.minecraft
        self.log = log

        self.players = {}

    def onEnable(self):
        self.api.registerHelp("WorldEdit", "Terrain modification commands", [
            ("//wand", "Gives you a wooden axe that can be used with WorldEdit", "worldedit.wand"),
            ("//set <TileName> [dataValue]", "Fills the selected region with the specified material.", "worldedit.set"),
            ("//replace <from> <SquareRadius>",
             "Replaces the specified region from the specified material to the other specified material.",
             "worldedit.fill"),
            ("//fill <TileName> <SquareRadius>",
             "Fills in a square radius around the player with the specified material.", "worldedit.fill"),
            ("//hfill <TileName> <SquareRadius>",
             "Fills in a hollow square radius around the player with the specified material.", "worldedit.hfill"),
            ("//pos1", "Sets point 1 at player's position. Same as left-clicking with wooden axe.", "worldedit.pos1"),
            ("//pos2", "Sets point 2 at player's position. Same as right-clicking with wooden axe.", "worldedit.pos2"),
            ("//replacenear <from-block> <to-block> <SquareRadius>",
             "Replaces all blocks within the specified square radius from specified block to specified block.",
             "worldedit.replacenear"),
            ("//extinguish <SquareRadius>", "Removes all fire from the player in the specified square radius.",
             "worldedit.extinguish"),
        ])

        self.api.registerCommand("/wand", self.command_wand, "worldedit.wand")
        self.api.registerCommand("/set", self.command_set, "worldedit.set")
        self.api.registerCommand("/fill", self.command_fill, "worldedit.fill")
        self.api.registerCommand("/replace", self.command_replace, "worldedit.replace")
        self.api.registerCommand("/hfill", self.command_hollow_fill, "worldedit.hfill")
        self.api.registerCommand("/pos1", self.command_pos1, "worldedit.pos1")
        self.api.registerCommand("/pos2", self.command_pos2, "worldedit.pos2")
        self.api.registerCommand("/replacenear", self.command_replaceNear, "worldedit.replacenear")
        self.api.registerCommand("/extinguish", self.command_extinguish, "worldedit.extinguish")
        self.api.registerEvent("player.place", self.action_rightclick)
        self.api.registerEvent("player.dig", self.action_leftclick)

        # for quick testing:
        # self.api.registerPermission("worldedit.wand", True)
        # self.api.registerPermission("worldedit.set", True)
        # self.api.registerPermission("worldedit.fill", True)
        # self.api.registerPermission("worldedit.replace", True)
        # self.api.registerPermission("worldedit.hfill", True)
        # self.api.registerPermission("worldedit.pos1", True)
        # self.api.registerPermission("worldedit.pos2", True)
        # self.api.registerPermission("worldedit.replacenear", True)
        # self.api.registerPermission("worldedit.extinguish", True)



    def onDisable(self):
        pass

    def getMemoryPlayer(self, name):
        if name not in self.players:
            self.players[name] = {"sel1": None, "sel2": None}
        return self.players[name]

    # events
    def action_leftclick(self, payload):
        player, action = payload["player"], payload["action"]
        if player.hasPermission("worldedit.pos1"):
            p = self.getMemoryPlayer(player.username)
            item = player.getHeldItem()
            if item is None:
                return
            if item["id"] == 271 and (action == "begin_break"):
                p["sel1"] = payload["position"]
                player.message("&dPoint one selected.")
                return False

    def action_rightclick(self, payload):
        player = payload["player"]
        if player.hasPermission("worldedit.pos2"):
            p = self.getMemoryPlayer(player.username)
            try:
                if payload["item"]["id"] == 271:
                    p["sel2"] = payload["position"]
                    player.message("&dPoint two selected.")
                    return False
            except:
                pass

    def command_wand(self, player, args):
        self.minecraft.console("give %s wooden_axe 1" % player.username)
        player.message("&bRight click two areas with this wooden axe tool to select a region.")

    def command_fill(self, player, args):
        if len(args) > 1:
            try:
                block = args[0]
                size = int(args[1]) / 2
                pos = player.getPosition()
                self.minecraft.getWorld().fill((pos[0] - size, pos[1] - size, pos[2] - size),
                                               (pos[0] + size, pos[1] + size, pos[2] + size), block)
                # self.minecraft.console("execute %s ~ ~ ~ fill ~%d ~%d ~%d ~%d ~%d ~%d %s" %
                # (player.username, size, size, size, -size, -size, -size, block))
            except:
                print(traceback.format_exc())
                player.message("&cError: <TileName> must be a string and <SquareRadius> must be an integer.")
        else:
            player.message("&cUsage: //fill <TileName> <SquareRadius>")

    def command_hollow_fill(self, player, args):
        if len(args) > 1:
            try:
                block = args[0]
                size = int(args[1]) / 2
                pos = player.getPosition()
                self.minecraft.getWorld().fill((pos[0] - size, pos[1] - size, pos[2] - size),
                                               (pos[0] + size, pos[1] + size, pos[2] + size),
                                               block, 0, "hollow")
            except:
                print(traceback.format_exc())
                player.message("&cError: <TileName> must be a string and <SquareRadius> must be an integer.")
        else:
            player.message("&cUsage: //hfill <TileName> <SquareRadius>")

    def command_replace(self, player, args):
        if len(args) > 1:
            try:
                block1 = args[0]
                block2 = args[1]
                p = self.getMemoryPlayer(player.username)
                if p["sel1"] and p["sel2"]:
                    self.minecraft.getWorld().replace(p["sel1"], p["sel2"], block1, 0, block2, 0)
                else:
                    player.message("&cPlease select two regions with the wooden axe tool. Use //wand to obtain one.")
            except:
                print(traceback.format_exc())
                player.message("&cSorry, something went wrong.")
        else:
            player.message("&cUsage: //replace <from-block> <to-block>")

    def command_set(self, player, args):
        p = self.getMemoryPlayer(player.username)
        datavalue = 0
        if len(args) == 2:
            datavalue = int(args[1])
        if len(args) > 0:
            if p["sel1"] and p["sel2"]:
                pos = " ".join(([str(i) for i in p["sel1"]]))
                pos += " "
                pos += " ".join(([str(i) for i in p["sel2"]]))
                self.minecraft.console("fill %s %s %d" % (pos, args[0], datavalue))
            else:
                player.message("&cPlease select two regions with the wooden axe tool. Use //wand to obtain one.")
        else:
            player.message("&cUsage: //set <TileName> [dataValue]")

    def command_pos1(self, player, args):
        p = self.getMemoryPlayer(player.username)
        if len(args) == 0:
            p["sel1"] = player.getPosition()
        player.message({"text": "Set position 1 to %s." % (str(player.getPosition())), "color": "light_purple"})

    def command_pos2(self, player, args):
        p = self.getMemoryPlayer(player.username)
        if len(args) == 0:
            p["sel2"] = player.getPosition()
        player.message({"text": "Set position 2 to %s." % (str(player.getPosition())), "color": "light_purple"})

    def command_replaceNear(self, player, args):
        try:
            i1, i2, radius = args
            radius = int(radius)
        except:
            player.message("&cUsage: //replacenear <from-block> <to-block> <SquareRadius>")
            return
        self.minecraft.console("execute %s ~ ~ ~ fill ~-%d ~-%d ~-%d ~%d ~%d ~%d %s %d replace %s %d" %
                               (player.username, radius/2, radius/2, radius/2, radius/2,
                                radius/2, radius/2, i2, 0, i1, 0))

    def command_extinguish(self, player, args):
        try:
            radius = int(args[0])
        except:
            player.message("&cUsage: //extinguish <SquareRadius>")
            return
        self.minecraft.console("execute %s ~ ~ ~ fill ~-%d ~-%d ~-%d ~%d ~%d ~%d %s %d replace %s" %
                               (player.username, radius/2, radius/2, radius/2, radius/2,
                                radius/2, radius/2, "air", 0, "fire"))
