import datetime

from todoist.api import TodoistAPI
import notion
from notion.client import NotionClient
import json
from bidict import bidict

class task:

    def __init__(self,
                 source=None,
                 task_id=None,
                 notion_task_id=None,
                 content=None,
                 done=None,
                 due=None,
                 label_ids=None,
                 label_names=None,
                 project_id=None,
                 notion_project_id=None,
                 project_name=None,
                 todoist_note_id=None,
                 ):

        self.source = source
        self.task_id = task_id
        self.content = content
        self.done = done
        self.due = due
        self.label_ids = label_ids
        self.label_names = label_names
        self.project_id = project_id
        self.project_name = project_name
        self.notion_task_id = notion_task_id
        self.notion_project_id = notion_project_id
        self.todoist_note_id = todoist_note_id

    def __repr__(self):
        return f"Task: {self.content}\n {json.dumps(self.__dict__, indent=4)}"

    def __eq__(self, other):
        return self.generate_eq_dict() == other.generate_eq_dict()

    def __getattr__(self, attr):
        return self.__dict__[attr]

    def __setattr__(self, name, value):
        super.__setattr__(self, name, value)

    def generate_eq_dict(self):

        _eq = (self.task_id, self.notion_task_id)

        return _eq

    def update(self, **kwargs):

        # check that all kwargs are valid:
        for kwarg in kwargs:
            if kwarg not in self.__dict__.keys():
                raise ValueError(f"{kwarg} is not a valid task parameter.")

        for name, value in kwargs.items():
            super.__setattr__(self, name, value)


class taskManager:

    def __init__(self, todoist_token, notion_token, notion_settings_url):

        self.api = TodoistAPI(todoist_token)
        self.client = NotionClient(token_v2=notion_token)
        self.settings = self.client.get_collection_view(notion_settings_url)
        self.config = {row.title: row.value for row in self.settings.collection.get_rows()}  # extract settings
        self.tasks = self.client.get_collection_view(
            "https://www.notion.so/" + self.config["Link to task database"]
            )
        self.projects = self.client.get_collection_view(
            "https://www.notion.so/" + self.config["Link to project database"]
            )
        self.labels = self.client.get_collection_view(
            "https://www.notion.so/" + self.config["Link to label database"]
            )

        # initialize todoist api jsons
        self.old_sync = None
        self.new_sync = None
        self.old_commit = None
        self.new_commit = None

    def sync_todoist_api(self):

        self.old_sync = self.new_sync
        self.new_sync = self.api.sync()

    def commit_todoist_api(self):
        self.old_commit = self.new_commit
        self.new_commit = self.api.commit()


class labelManager:

    @staticmethod
    def label_translator(label, output="todoist"):

        if output == "todoist":
            return label.replace(" ", "")

    @staticmethod
    def get_labels_bidict(manager):

        label_bidict = bidict({})
        for label in manager.api.labels.all():
            label_bidict[label["id"]] = label["name"]

        return label_bidict

    @staticmethod
    def sync_labels_to_todoist(manager: taskManager):

        print("Syncing labels...")
        new_label_count = 0
        updated_label_count = 0

        # sync todoist api
        manager.sync_todoist_api()

        # get a list of labels
        labels = labelManager.get_labels_bidict(manager)

        # go label by label
        for row in manager.labels.collection.get_rows():
            # first check if it has a TodoistID
            if row.todoistID is None:
                # check if the name of the label matches one on todoist
                if row.todoist_name in labels.values():
                    # add todoist label id to notion
                    row.todoistID = labels.inverse[row.todoist_name]
                else:  # otherwise, add it to todoist
                    print(f"Adding new label {row.todoist_name}")
                    manager.api.labels.add(name=row.todoist_name)
                    manager.commit_todoist_api()

                    # update label_bidict and add todoistID to notion
                    labels = labelManager.get_labels_bidict(manager)
                    row.todoistID = labels.inverse[row.todoist_name]

                    new_label_count += 1 # update label count
            else:
                # check if the name is different, if so, update name in todoist
                if row.todoist_name != labels[row.todoistID]:
                    print(f"Updating label {labels[row.todoistID]} ⮕ {row.todoist_name}")
                    manager.api.labels.get_by_id(row.todoistID).update(name=row.todoist_name)
                    manager.commit_todoist_api()

                    updated_label_count += 1  # update updated label count

            # add notion IDs to table
            # for notion_label in manager.tasks.collection.get_schema_property():

        print(f"Done syncing labels. {new_label_count} label(s) added and {updated_label_count} label(s) updated")


class taskImporter:

    @staticmethod
    def from_todoist(api, item):

        is_done = True if item["checked"] == 1 else False

        # check if there is a notion task ID in notes:
        notion_id = None
        for note in api.notes.all():
            if note["item_id"] == item["id"] and "NotionID" in note["content"]:
                notion_note_id = note["id"]
                notion_id = note["content"][10:]

        # check if due data available
        try:
            due = item["due"]["date"]
        except TypeError:
            due = None

        new_task = task(
            source="todoist",
            task_id=item["id"],
            content=item["content"],
            done=is_done,
            due=due,
            label_ids=item["labels"],
            label_names=[api.labels.get_by_id(label)['name'] for label in item['labels']],
            project_id=item["project_id"],
            project_name=api.projects.get_by_id(item['project_id'])['name'],
            notion_project_id=notion_id
        )

        return new_task

    @staticmethod
    def from_notion(item):

        is_done = True if item.status == "Done 🙌" else False
        todoist_label_id, todoist_label = \
            taskImporter.label_translator(output="todoist", notion_label=item.status)

        # add notion ID to the task table
        item.NotionID = item.id

        new_task = task(
            source="notion",
            task_id=item.TodoistID,
            content=item.title,
            done=is_done,
            due=item.due.start.strftime(format="%Y-%m-%d"),
            label_ids=[todoist_label_id],
            label_names=[todoist_label],
            project_id=item.project[0].TodoistID,
            project_name=item.project[0].title,
            notion_task_id=item.id,
            notion_project_id=item.project[0].id,

        )

        return new_task

    @staticmethod
    def to_notion(item, notion_table, project_table):

        notion_table.refresh()

        if not isinstance(item, task):
            raise TypeError("Input task must be of class `taskImporter.task`.")

        if not isinstance(notion_table, notion.block.CollectionViewPageBlock):
            raise TypeError("Input table must be of `notion.block.CollectionViewPageBlock` type.")

        status = "Done 🙌" if item.done else \
            taskImporter.label_translator(output="notion", todoist_id=item.label_ids[0])[1]

        project = project_table.collection.get_rows(search=str(item.project_id))[0]

        group = project.group[0]

        new_row = notion_table.collection.add_row()
        new_row.name = item.content
        new_row.TodoistID = item.task_id
        new_row.due = notion_table.collection.NotionDate(start=datetime.datetime.strptime(item.due, "%Y-%m-%d").date())
        new_row.status = status
        new_row.project = project
        new_row.NotionID = new_row.id
        new_row.group = group

        print(f"Imported task {item.content} with status {status}")

    @staticmethod
    def to_todoist(item, api):

        sync_message = api.sync()

        api.items.add(content=item.content,
                      due={"date": item.due},
                      labels=item.label_ids,
                      project_id=item.project_id, )

        item_commit = api.commit()
        new_item_id = item_commit['items'][0]['id']

        note = api.notes.add(new_item_id, f"NotionID: {item.notion_task_id}")
        note_commit = api.commit()
        new_note_id = note_commit['notes'][0]['id']

        return new_item_id, new_note_id

    @staticmethod
    def from_webhook(api, request_args):

        args = request_args

        is_done = True if args.get("checked") == 1 else False

        # check if there is a notion task ID in notes:
        notion_id = None
        for note in api.notes.all():
            if note["item_id"] == args.get('id') and "NotionID" in note["content"]:
                notion_note_id = note["id"]
                notion_id = note["content"][10:]

        # check if due data available
        try:
            due = args.get("due")["date"]
        except TypeError:
            due = None
        print("LABELS:")
        print([int(args.get('labels'))])
        print(api.labels.get_by_id(int(args.get('labels'))))
        print(api.labels.get_by_id(int(args.get('labels')))['name'])

        new_task = task(
            source="todoist",
            task_id=args.get('id'),
            content=args.get('content'),
            done=is_done,
            due=due,
            label_ids=[int(args.get('labels'))],
            label_names=[api.labels.get_by_id(label)['name'] for label in [int(args.get('labels'))]],
            project_id=args.get('project_id'),
            project_name=api.projects.get_by_id(int(args.get('project_id')))['name'],
            notion_project_id=notion_id
        )

        return new_task
