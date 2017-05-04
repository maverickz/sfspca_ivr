#!/usr/bin/env python

from flask import Flask, request, redirect, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import json
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

    # Gather digits.
    with resp.gather(numDigits=1, action="/handle-key", method="POST") as gather:
        gather.say("""Hello, thanks for calling SFSPCA's application.
                      Press 1 to record your awesome story.
                      Press any other key to start over.""", voice="alice")
    # If the user doesn't select an option, redirect them into a loop
    resp.redirect("/welcome")
    return twiml(resp)


def _redirect_welcome():
    response = VoiceResponse()
    response.say("Returning to the main menu", voice="alice")
    return redirect("/welcome")


@app.route("/handle-key", methods=['GET', 'POST'])
def handle_key():
    """Handle key press from a user."""

    digit_pressed = request.values.get('Digits', None)
    logger.info("Digit pressed: {}".format(digit_pressed))
    if digit_pressed == "1":
        resp = VoiceResponse()
        resp.say("""Record your story after the tone. Please keep your recording to under a minute.
                    Once you have finished recording, you may hangup""", voice="alice")
        resp.record(maxLength="60", action="/handle-recording")
        return str(resp)

    # If the caller pressed anything but 1, redirect them to main menu
    else:
        return _redirect_welcome()


@app.route("/handle-message", methods=['GET', 'POST'])
def handle_message():
    """Capture and store an image from the user, if any"""
    resp = ""
    from_number = request.values.get('From', None)
    img_url = request.values.get("MediaUrl0", None)

    save_media(from_number, img_url=img_url)
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
        logger.info("Recording saved for {}".format(from_number))
        recordings_obj["recordings"].append(recording_url)
    if img_url is not None:
        logger.info("Image saved for {}".format(from_number))
        recordings_obj["images"].append(img_url)
    redis_client.set(str(from_number), json.dumps(recordings_obj))


def send_confirmation_text(from_number):
    message = client.messages.create(to=str(from_number),
                                     from_="+14152003278",
                                     body="Thanks for sharing your story, please respond with a photo, if available")
    logger.info("Message to {}, status: {}".format(from_number, message))


@app.route("/get-stories", methods=['GET'])
def get_stories():
    user_stories = {}
    print redis_client.scan_iter()
    for key in redis_client.scan_iter():
        user_stories[key] = redis_client.get(key)
    return user_stories

if __name__ == "__main__":
    port = os.getenv("PORT", 8080)
    app.run(debug=True, host='0.0.0.0', port=int(port))
