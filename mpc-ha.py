#!/usr/bin/env python3
#
# Copyright 2019,2021-2023  Simon Arlott
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

import logging
import logging.handlers
import mpd
import os
import requests
import sys
import yaml

password, hostname = os.environ["MPD_HOST"].split("@")
with open("config.yaml", "r") as f:
	config = yaml.safe_load(f)

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {config['homeassistant']['token']}"})

log = logging.getLogger("mpc-ha")

last_enabled = set()
last_disabled = set()

def switch(output, state):
	name = config["speakers"][output].get("switch")
	if name:
		resp = session.post(f"{config['homeassistant']['url']}/api/services/switch/turn_{state}", json={"entity_id": name})
		if resp.status_code != 200:
			self.log.error(f"Failed to change power status for {name} to {state}: {resp.status_code} {resp.text}")

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
		if output["outputname"] in config["doorbell"]:
			if int(output["outputenabled"]) == 1:
				log.info("Doorbell")
				if client.status()["state"] == "play":
					log.info("Pause (for doorbell)")
					client.pause()
				command = config["doorbell"][output["outputname"]].get("command")
				if command:
					os.posix_spawnp("sh", ["sh", "-c", command], {})
				client.disableoutput(output["outputid"])

	auto_on = False

	if now_enabled != last_enabled:
		for output in (now_enabled - last_enabled):
			log.info("Enable " + output)
			switch(output, "on")
			if config["speakers"][output].get("auto", True):
				auto_on = True

	if not first:
		if last_enabled and not now_enabled:
			log.info("Pause (all now disabled)")
			client.pause()
			os.spawnlp(os.P_NOWAIT, "sh", "sh", "-c", config["stop_command"])
		elif auto_on and not last_enabled and now_enabled:
			if client.status()["state"] == "pause" and subprocess.run(config["auto_command"], shell=True).returncode == 0:
				log.info("Resume")
				client.play()

	if not now_enabled and client.status()["state"] == "play":
		log.info("Pause (none enabled)")
		client.pause()
		os.spawnlp(os.P_NOWAIT, "sh", "sh", "-c", config["stop_command"])

	if now_disabled != last_disabled:
		for output in (now_disabled - last_disabled):
			log.info("Disable " + output)
			switch(output, "off")

	last_enabled = now_enabled
	last_disabled = now_disabled

	status = client.status()
	if config.get("consume-auto-off"):
		if status["state"] == "stop" and int(status["consume"]) == 1 and int(status["playlistlength"]) == 0:
			log.info("Consume finished, disabling all outputs")
			client.consume(0)
			for output in client.outputs():
				if output["outputname"] in config["speakers"]:
					if int(output["outputenabled"]) == 1:
						client.disableoutput(output["outputid"])

	if int(status["volume"]) not in [-1, 100]:
		log.info("Set volume to 100%")
		client.setvol(100)


if __name__ == "__main__":
	root = logging.getLogger()
	root.setLevel(level=logging.DEBUG)

	handler = logging.StreamHandler(sys.stdout)
	handler.setLevel(level=logging.DEBUG)
	handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
	root.addHandler(handler)

	handler = logging.handlers.SysLogHandler("/dev/log")
	handler.setLevel(level=logging.INFO)
	handler.setFormatter(logging.Formatter("mpc-ha: %(levelname)s %(name)s: %(message)s"))
	root.addHandler(handler)

	client = mpd.MPDClient()
	client.connect(hostname, 6600)
	client.password(password)

	update_outputs(client, True)
	while client.idle("player", "output", "mixer"):
		update_outputs(client)
