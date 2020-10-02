import os

import notion
from todoist.api import TodoistAPI
from notion.client import NotionClient
from flask import Flask, request, jsonify


app = Flask(__name__)


def createNotionTask(token, collectionURL, content):
    # notion
    client = NotionClient(token)
    cv = client.get_collection_view(collectionURL)
    row = cv.collection.add_row()
    row.title = content


@app.route('/from_webhook', methods=['GET'])
def send_to_notion():

    api = TodoistAPI("439fa9618e0338718f3f9293433df2911674edad")

    # convert webhook task to custom task class
    new_task = taskImporter.from_webhook(api=api, request_args=request.args)

    print(new_task.__dict__)

    return jsonify({'status': 'accepted'}), 200
    

@app.route('/create_todo', methods=['GET'])
def create_todo():

    todo = request.args.get('todo')
    token_v2 = os.environ.get("TOKEN")
    url = os.environ.get("URL")
    createNotionTask(token_v2, url, todo)
    return f'added {todo} to Notion'


if __name__ == '__main__':
    app.debug = True
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
