import os

from notion.client import NotionClient
from flask import Flask, request, jsonify, Response, redirect, g
import base64
import hashlib
import hmac
import requests


app = Flask(__name__)


def compute_hmac(body):

    signature = base64.b64encode(hmac.new(
        "ab9df4df62681fd519648c413750c611cad02048".encode('utf-8'),
        body,
        digestmod=hashlib.sha256).digest()).decode('utf-8')
    return signature


@app.route("/webhook", methods=["POST"])
def respond():

    request_hmac = request.headers.get('X-Todoist-Hmac-SHA256')
    calculated_hmac = compute_hmac(request.get_data())
    if request_hmac == calculated_hmac:
        print(f"HMACs match! {request_hmac}")
    else:
        print("Dont match!")

    data = request.json
    print(data['event_name'])
    print(data['event_data']['id'])
    return Response(status=200)


@app.route("/test", methods=["GET"])
def testing_get():

    print("TESTING GOT!")
    return Response(status=200)


def post_todoist_oauth(code, state):

    url = "https://todoist.com/oauth/access_token"
    params = {"code": code, "state": state}


@app.route("/auth")
def enter():
    print(request.args)
    code = request.args.get("code")
    state = request.args.get("state")

    print(f"\n\nCode: {code}\nState: {state}")

    return redirect("https://todoist.com/", code=302)

    
if __name__ == '__main__':
    app.debug = True
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
