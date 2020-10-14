import os
from flask import Flask, request, Response, redirect
import base64
import hashlib
import hmac
import tools
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)


def compute_hmac(body):

    signature = base64.b64encode(hmac.new(
        os.environ["TODOIST_CLIENT_SECRET"].encode('utf-8'),
        body,
        digestmod=hashlib.sha256).digest()).decode('utf-8')
    return signature


def check_notion_for_updates():
    print("\nChecking Notion for updates...")
    tools.labelManager.sync_labels_to_todoist(manager)
    tools.projectManager.sync_projects(manager)
    tools.taskManager.sync_notion_to_todoist(manager, full_sync=False)


@app.route("/webhook", methods=["POST"])
def respond():

    request_hmac = request.headers.get('X-Todoist-Hmac-SHA256')
    calculated_hmac = compute_hmac(request.get_data())
    if request_hmac == calculated_hmac:
        print(f"HMACs match! {request_hmac}")
        data = request.json
        print(data['event_name'])
        print(f"{data['event_data']['id']}: {data['event_data']['content']}")
        hook_job = scheduler.add_job(tools.taskManager.webhook_arrived, args=[manager, data])
        # tools.taskManager.webhook_arrived(manager, data)
        return Response(status=200)
    else:
        print("HMACs don't match!! Check this out!!!")
        return Response(status=400)


@app.route("/test", methods=["GET"])
def testing_get():

    print("TESTING GOT!")
    return Response("This is my site!", status=200)


@app.route("/auth")
def enter():
    print(request.args)
    code = request.args.get("code")
    state = request.args.get("state")

    print(f"\n\nCode: {code}\nState: {state}")

    return redirect("https://todoist.com/", code=302)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return redirect("https://todoist.com/", code=302)


# set up manager and schedule todoist updater
manager = tools.syncManager(
        todoist_token=os.environ["TODOIST_TOKEN"],
        notion_token=os.environ["NOTION_TOKEN"],
        notion_settings_url=os.environ["NOTION_SETTINGS"],
    )

scheduler = BackgroundScheduler(daemon=True)
notion_job = scheduler.add_job(check_notion_for_updates, 'interval', minutes=3)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown(wait=False))

    
if __name__ == '__main__':

    app.debug = True
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
