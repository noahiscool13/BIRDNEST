"""
1. List of drones that have been in the NDZ
2. Every drone in the list must have a timestamp of when it was last in the NDZ
3. The list must be updated every 2 seconds
"""
import json
import time
from threading import Thread

import requests
import xml.etree.ElementTree as ET
from math import dist

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

origins = ["*", ]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Drone:
    def __init__(self, serialNumber, model, manufacturer, mac, ipv4, ipv6, firmware, positionY, positionX, altitude):
        self.serialNumber = serialNumber
        self.model = model
        self.manufacturer = manufacturer
        self.mac = mac
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.firmware = firmware
        self.positionY = positionY
        self.positionX = positionX
        self.altitude = altitude

    @staticmethod
    def from_xml(data):
        return Drone(data.find('serialNumber').text, data.find('model').text, data.find('manufacturer').text,
                     data.find('mac').text, data.find('ipv4').text, data.find('ipv6').text, data.find('firmware').text,
                     float(data.find('positionY').text), float(data.find('positionX').text),
                     float(data.find('altitude').text))

    def __eq__(self, other):
        return self.serialNumber == other.serialNumber

    def __hash__(self):
        return hash(self.serialNumber)

    @property
    def dist_to_ndz(self):
        return dist((self.positionX, self.positionY), (250_000, 250_000))


def make_drone_locations_request():
    try:
        url = "http://assignments.reaktor.com/birdnest/drones"
        resp = requests.get(url)
        root = ET.fromstring(resp.text)
        return list(map(Drone.from_xml, root.find("capture").findall("drone")))
    except Exception as e:
        print("EXCEPT", e)
        return []


def get_pilot_info(drone):
    try:
        serial_number = drone.serialNumber
        url = f"http://assignments.reaktor.com/birdnest/pilots/{serial_number}"
        res = json.loads(requests.get(url).text)
        return Pilot(res["pilotId"], res["firstName"], res["lastName"], res["email"], res["phoneNumber"], drone,
                     time.time())
    except Exception as e:
        print("EXCEPT", e)
        return Pilot("Unknown", "Unknown", "Unknown", "Unknown", "Unknown", drone, time.time())


class Pilot:
    def __init__(self, pilot_id, first_name, last_name, email, phone, drone, last_seen):
        self.pilot_id = pilot_id
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.phone = phone
        self.drone = drone
        self.last_seen = last_seen

    def to_dict(self):
        return {
            "pilot_id": self.pilot_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "dist": self.drone.dist_to_ndz,
            "last_seen": self.last_seen
        }


violations = dict()


@app.get("/")
async def root():
    return [v.to_dict() for v in violations.values()]


def update_violations():
    global violations
    drones = make_drone_locations_request()
    for drone in drones:
        if drone.dist_to_ndz < 100_000:
            if drone.serialNumber in violations:
                violations[drone.serialNumber].last_seen = time.time()
                if violations[drone.serialNumber].first_name == "Unknown":
                    violations[drone.serialNumber] = get_pilot_info(drone)
                if violations[drone.serialNumber].drone.dist_to_ndz > drone.dist_to_ndz:
                    violations[drone.serialNumber].drone = drone
            else:
                violations[drone.serialNumber] = get_pilot_info(drone)
    violations = {k: v for k, v in violations.items() if time.time() - v.last_seen < 600}

    time.sleep(2)


def violation_loop():
    while True:
        update_violations()


thread = Thread(target=violation_loop)
thread.start()
