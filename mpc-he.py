#!/usr/bin/env python3
#
# Copyright 2019,2021  Simon Arlott
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import mpd
import os
import subprocess
import yaml

password, hostname = os.environ["MPD_HOST"].split("@")
with open("config.yaml", "r") as f:
	config = yaml.load(f)


last_enabled = set()
last_disabled = set()

def transmit(output, state):
	address = config["speakers"][output].get("address")
	if address:
		subprocess.call(["../rf433-ook/encoders/HomeEasyV3.py", str(address[0]), "-d", str(address[1]), state, "-p", config["transmitter"]])

def update_outputs(client, first=False):
	global last_enabled, last_disabled

	now_enabled = set()
	now_disabled = set()

	for output in client.outputs():
		if output["outputname"] in config["speakers"]:
			if int(output["outputenabled"]) == 1:
				now_enabled.add(output["outputname"])
			else:
				now_disabled.add(output["outputname"])

	auto_on = False

	if now_enabled != last_enabled:
		for output in (now_enabled - last_enabled):
			print("Enable " + output)
			transmit(output, "on")
			if config["speakers"][output].get("auto", True):
				auto_on = True

	if not first:
		if last_enabled and not now_enabled:
			print("Pause")
			client.pause()
		elif auto_on and not last_enabled and now_enabled:
			if client.status()["state"] == "pause":
				print("Resume")
				client.play()

	if not now_enabled and client.status()["state"] == "play":
		print("Pause")
		client.pause()

	if now_disabled != last_disabled:
		for output in (now_disabled - last_disabled):
			print("Disable " + output)
			transmit(output, "off")

	last_enabled = now_enabled
	last_disabled = now_disabled

	if config.get("consume-auto-off"):
		status = client.status()
		if status["state"] == "stop" and int(status["consume"]) == 1 and int(status["playlistlength"]) == 0:
			print("Consume finished, disabling all outputs")
			client.consume(0)
			for output in client.outputs():
				if output["outputname"] in config["speakers"]:
					if int(output["outputenabled"]) == 1:
						client.disableoutput(output["outputid"])


client = mpd.MPDClient()
client.connect(hostname, 6600)
client.password(password)

update_outputs(client, True)
while client.idle("player", "output"):
	update_outputs(client)
