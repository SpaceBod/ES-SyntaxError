import board
import busio
import RPi.GPIO as GPIO
from digitalio import DigitalInOut
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
from adafruit_pn532.i2c import PN532_I2C
import time
import socket
from datetime import datetime, date
import json
import requests
import numpy as np
from picamera import PiCamera
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

# ANPR Server
ip = '146.169.178.115'
port = 1003

# DB
db = "https://embedded-systems-cf93d-default-rtdb.europe-west1.firebasedatabase.app/"

# Define the private key file (change to use your private key)
keyfile = "/home/pi/python/embedded-systems-cf93d-firebase-adminsdk-amky8-e0a50b80ba.json"

# Define the required scopes
scopes = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/firebase.database"
]

# Authenticate a credential with the service account (change to use your private key)
credentials = service_account.Credentials.from_service_account_file(keyfile, scopes=scopes)

# Use the credentials object to authenticate a Requests session.
authed_session = AuthorizedSession(credentials)

onlineUsers = set()


camera = PiCamera()

senddate = 0
endtime = 0

# Add RFID
def rfiduserinout(card, inout):
    global senddate 
    senddate = date.today()
    global sendtime 
    sendtime = datetime.now().strftime("%H:%M:%S")
    path = f"rfidcards/{card}/{senddate}.json"

    read = requests.get(db + path)

    if read.json() is not None:
        data = read.json()
        if "Out" not in list(read.json().keys()):
            data["Out"] = []
        if "In" not in list(read.json().keys()):
            data["In"] = []
            
            
    else:
        data = {"In":[], "Out":[]}
	
	
	
    if inout == "in":
    	
        data["In"].append(sendtime)

    else:
        data["Out"].append(sendtime)
    
    #print(data)
    resp = requests.put(db + path, json=data)

    if resp.ok:
        print("Ok")
    else:
        raise

# LEDs
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(27,GPIO.OUT)
GPIO.setup(17,GPIO.OUT)
red_led = 17
green_led = 27
high = GPIO.HIGH
low = GPIO.LOW

# RFID
i2cRFID = busio.I2C(board.SCL, board.SDA)
reset_pin = DigitalInOut(board.D6)
req_pin = DigitalInOut(board.D12)
pn532 = PN532_I2C(i2cRFID, debug=False, reset=reset_pin, req=req_pin)


# Configure PN532 to communicate with MiFare cards
pn532.SAM_configuration()


# Display
serial = i2c(port=1, address=0x3C)
device = sh1106(serial, rotate=0)

title1 = 'Welcome!'
title2 = 'Please scan ID...'
title3 = 'ACCEPTED'
title4 = 'PROCEED'
titleIN = 'Status: IN'
titleRecommended = 'RECOMMENDED'
titleSpace = 'SPACE:'

UID_title = 'ID: '

def takePicture(uid):
    camera.capture("pictures/{}_{}_{}.jpg".format(uid, senddate, sendtime))
    print("IMG Taken.")
     

def ANPR(uid):
    takePicture(uid)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((ip, port))
    print("Sending")
    
    image_name = "pictures/{}_{}_{}.jpg".format(uid, senddate, sendtime)
    client.send(image_name.encode())
    file = open(image_name, 'rb')
    image_data = file.read(2048)
    
    while image_data:
        client.send(image_data)
        image_data = file.read(2048)
    
        
    file.close()

    client.close()

def led(colour, status):
    GPIO.output(colour, status)

def checkSignIn(uid):
    # Checks if signing in / out
    # If ID already signed in, remove ID from set
    if uid in onlineUsers:
        print('ID:', uid, '\tSigned Out')
        onlineUsers.remove(uid)
        return False
    # Else add ID to set
    else:
        print('ID:', uid, '\tSigned In')
        onlineUsers.add(uid)
        return True


def getfreetype(type_):
    path = "parkingspaces.json"
    query = "?orderBy=\"Free\"&equalTo=\"True\""
    resp = requests.get(db+path+query)
    free = resp.json()
    filtered = {}
    for space in free:
        if free[space]["Type"] == type_:
            filtered[space] = free[space]["Location"]
    return filtered
    

def getpreftype(card):
    prefpath = f"rfidcards/{card}/Preference.json"
    prefresp = authed_session.get(db + prefpath)
    pref = prefresp.json()
    if pref is None:
        pref = "Exit"
    typepath = f"rfidcards/{card}/Type.json"
    typeresp = authed_session.get(db + typepath)
    type_ = typeresp.json()
    if type_ is None:
        type_ = "Normal"
    return pref, type_


def recommendspace(pref, type_):
    spaces = getfreetype(type_)

    locations =[[0, 18], [36,18], [36,9]]
    if pref == "Exit":
        exit = np.array(locations[0])
    elif pref == "Car Park Entrance":
        exit = np.array(locations[1])
    else:
        exit = np.array(locations[2])

    mindist = 9999
    mindistspace = -1
    nums = list(spaces.keys())

    for num in nums:
        dist = np.linalg.norm(np.array(spaces[num]) - exit)
        if dist < mindist:
            mindist = dist
            mindistspace = num
    return mindistspace


def main():
    print("Waiting for RFID/NFC card...")
    led(red_led, high)
    
    while True:
        now = datetime.now().strftime("%H:%M")
        with canvas(device) as draw:
            draw.rectangle(device.bounding_box, outline="white", fill="black")
            draw.text((90, 8), now, fill="white")
            draw.text((10, 20), title1, fill="white")
            draw.text((10, 30), title2 , fill="white")
            
        # Check if a card is available to read
        uid = pn532.read_passive_target(timeout=0.5)
        
        # Try again if no card is available.
        if uid is None:
            continue
        
        # If card is detected:
        # Set Green LED ON and Red LED OFF
        led(green_led, high)
        led(red_led, low)
        
        # Convert User ID into string format
        uid = [hex(i) for i in uid]
        uid_string = ''.join(format(int(i, 16), '02x') for i in uid)
        
        # Accepted Display
        with canvas(device) as draw:
            draw.rectangle(device.bounding_box, outline="white", fill="black")
            draw.text((90, 8), now, fill="white")
            draw.text((40, 25), title3, fill="white")
        time.sleep(0.5)
        
        # Accepted + Proceed Display
        with canvas(device) as draw:
            draw.rectangle(device.bounding_box, outline="white", fill="black")
            draw.text((90, 8), now, fill="white")
            draw.text((40, 25), title3, fill="white")
            draw.text((44, 35), title4, fill="white")
        
        # Checks Status IN/OUT
        if checkSignIn(uid_string) == True:
            titleIN = "Status: IN"
            rfiduserinout(uid_string, "in")
            pref, type_ = getpreftype(uid_string)
            space = recommendspace(pref, type_)
        else:
            titleIN = "Status: OUT"
            rfiduserinout(uid_string, "out")
        
        # Status IN/OUT Displayed
        with canvas(device) as draw:
            draw.rectangle(device.bounding_box, outline="white", fill="black")
            draw.text((90, 8), now, fill="white")
            draw.text((33, 30), titleIN , fill="white")
        time.sleep(1)
        
        # Recommended Space
        if titleIN == "Status: IN":
            with canvas(device) as draw:
                draw.rectangle(device.bounding_box, outline="white", fill="black")
                draw.text((90, 8), now, fill="white")
                draw.text((30, 25), titleRecommended , fill="white")
                draw.text((40, 35), titleSpace + str(space), fill="white")
            
            ANPR(uid_string)
            time.sleep(2)
            
        led(green_led, low)
        led(red_led, high)
main()
