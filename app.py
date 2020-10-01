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

    # create task manager
    # manager = taskManager(
    #     todoist_token=os.environ.get("TODOIST_TOKEN"),
    #     notion_token=os.environ.get("NOTION_TOKEN"),
    #     notion_tasks_url=os.environ.get("NOTION_TASKS_URL"),
    #     notion_projects_url=os.environ.get("NOTION_PROJECTS_URL")
    # )
    # manager = taskManager(
    #     todoist_token="439fa9618e0338718f3f9293433df2911674edad",
    #     notion_token="https://www.notion.so/jarredgreen/807530144ad34fbdb80ef60b5d2c6abb?v=d42bd594d5ed4542b3a99da3a816dd04",
    #     notion_tasks_url="https://www.notion.so/jarredgreen/3b3056e9605d41eabc2116bbf90bdf5f?v=6cd80e6a373742e2bedb4c201eaf6f06",
    #     notion_projects_url="a2ae36c266053a72fc564b418a1f578d736228f614ab5925be62f22383894f550dd53004bb48005e699e101a94e00008d23fd6eff24286a48f62f943d3e427ddb14092ffcf94df25e58dd939bfc8"
    # )

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
