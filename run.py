#!/usr/bin/env python

from flask import Flask, request, redirect, url_for, Response
from pprint import pprint
from twilio.rest import Client
from datetime import date, datetime
from twilio.twiml.voice_response import VoiceResponse
import twilio.twiml
import json
import csv
import os
import redis
import sys
import logging


MYDIR = os.path.dirname(__file__)

# Read account sid and auth token from environmental variables
ACCOUNT_SID = os.getenv("ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

redis_client = redis.from_url(os.environ.get("REDIS_URL"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(log_format)
logger.addHandler(ch)

app = Flask(__name__)


def twiml(resp):
    resp = Response(str(resp))
    resp.headers['Content-Type'] = 'text/xml'
    return resp


@app.route("/welcome", methods=['GET', 'POST'])
def welcome():
    resp = VoiceResponse()
    resp.say("Hello, thanks for calling SFSPCA's Twilio app", voice="alice")

    # Gather digits.
    with resp.gather(numDigits=1, action=url_for("menu"), method="POST") as g:
        g.play(url="http://howtodocs.s3.amazonaws.com/et-phone.mp3", loop=3)
    return twiml(resp)


@app.route('/menu', methods=['POST'])
def menu():
    selected_option = request.form['Digits']
    option_actions = {'1': _give_instructions}

    if option_actions.has_key(selected_option):
        response = VoiceResponse()
        option_actions[selected_option](response)
        return twiml(response)

    return _redirect_welcome()


def _give_instructions(response):
    response.say("""Press 1 to record your awesome story.
                 Press any other key to start over.""", voice="alice")

    response.say("Hello, thanks for calling SFSPCA's application", voice="alice")

    response.hangup()
    return response


def _redirect_welcome():
    response = VoiceResponse()
    response.say("Returning to the main menu", voice="alice")
    response.redirect(url_for("welcome"))

    return twiml(response)


@app.route("/handle-key", methods=['GET', 'POST'])
def handle_key():
    """Handle key press from a user."""

    digit_pressed = request.values.get('Digits', None)
    logger.info("Digit pressed: {}".format(digit_pressed))
    if digit_pressed == "1":
        resp = VoiceResponse()
        resp.say("Record your story after the tone. Please keep your recording to under a minute. Once you have finished recording, you may hangup")
        resp.record(maxLength="60", action="/handle-recording")
        return str(resp)

    # If the caller pressed anything but 1, redirect them to the homepage.
    else:
        return redirect("/")


@app.route("/handle-message", methods=['GET', 'POST'])
def handle_message():
    """Capture and store an image from the user, if any"""
    resp = ""
    from_number = request.values.get('From', None)
    img_url = request.values.get("MediaUrl0", None)

    save_media(from_number, img_url=img_url)
    send_confirmation_text(from_number)
    if img_url is not None:
        resp = "Thanks for sharing the photo with us!"
    return resp


@app.route("/handle-recording", methods=['GET', 'POST'])
def handle_recording():
    """Save the user's recording"""

    from_number = request.values.get('From', None)

    resp = VoiceResponse()
    resp.say("Thanks for sharing your story, you will receive a text, please respond to it with a photo")
    # resp.play(recording_url)
    resp.say("Goodbye.")
    recording_url = request.values.get("RecordingUrl", None)
    save_media(from_number, recording_url=recording_url)
    send_confirmation_text(from_number)
    return str(resp)


def save_media(from_number, recording_url=None, img_url=None):
    recordings_json = redis_client.get(str(from_number))
    recordings_obj = json.loads(recordings_json) if recordings_json else {"recordings": [], "images": []}
    if recording_url is not None:
        recordings_obj["recordings"].append(recording_url)
    if img_url is not None:
        recordings_obj["images"].append(img_url)
    redis_client.set(str(from_number), json.dumps(recordings_obj))
    logger.info("Media saved for {}".format(from_number))


def send_confirmation_text(from_number):
    client.messages.create(to=str(from_number),
                           from_="+14152003278",
                           body="Thanks for sharing your story, please respond with a photo, if available")


if __name__ == "__main__":
    port = os.getenv("PORT", 8080)
    app.run(debug=True, host='0.0.0.0', port=int(port))
